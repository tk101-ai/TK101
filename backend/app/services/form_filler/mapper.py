"""자료 ↔ 양식 매핑 (FR-04, NFR-04 환각 방어 5개 방어선).

흐름:
1. 자료 청크 + 양식 변수 → Claude Sonnet 4.6
2. system 프롬프트 + 양식 본문은 prompt caching (잡 안 동일 양식 재호출 시 비용 절감)
3. 응답 JSON 파싱 → guardrails.sanitize_mappings 로 5개 방어선 적용
4. accepted/rejected 분리 반환 — 라우터가 form_mappings 저장 + 누락 보강 큐 분리

환각 방어 5개 방어선 적용 위치 (NFR-04):
- #1 DB CHECK: alembic 007 (T5-A)
- #2 confidence 임계: guardrails.filter_low_confidence
- #3 토큰 grounding: guardrails.verify_token_grounding
- #4 검수 강제: routers/forms.py 의 status 전이 가드
- #5 출처 메타 5종: 본 파일의 SourcePayload 강제 + guardrails.validate_mapping
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import settings
from app.services.form_filler import guardrails, prompts
from app.services.llm.client import LLMResponse, call_claude

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourcePayload:
    """매핑 입력으로 들어가는 자료 청크 1개.

    source_id: form_data_sources.id (UUID 문자열) — DB 화이트리스트로 검증됨.
    kind: nas_file | user_upload | user_input | web_search
    excerpt: 청크 본문 (Claude에 그대로 전달)
    file_path: 디버그/검수 UI 표시용
    """

    source_id: str
    kind: str
    excerpt: str
    file_path: str | None = None


@dataclass(frozen=True)
class VariablePayload:
    """매핑 입력으로 들어가는 양식 변수 1개."""

    key: str
    label: str
    type: str


@dataclass(frozen=True)
class MappingResult:
    """1건 매핑 정규화 결과 + 출처 메타 5종 (NFR-04 #5)."""

    variable_key: str
    value: str | None
    source_id: str | None
    source_excerpt: str | None
    llm_confidence: float
    reasoning: str
    rejected_reason: str | None = None  # 가드레일 거부 사유 (none이면 accepted)


@dataclass(frozen=True)
class MappingRunResult:
    """매핑 1회 호출 결과. 라우터가 form_mappings 저장 + form_jobs 비용 누적."""

    accepted: list[MappingResult]
    rejected: list[MappingResult]
    llm_response: LLMResponse


def _serialize_variables(variables: list[VariablePayload]) -> str:
    return json.dumps(
        [
            {"key": v.key, "label": v.label, "type": v.type}
            for v in variables
        ],
        ensure_ascii=False,
    )


# 자료 신뢰 우선순위(작을수록 먼저) — 업로드/직접입력을 1순위로 노출해
# LLM 이 충돌 시 이들을 우선하도록 유도(프롬프트 규칙과 짝).
_SOURCE_KIND_PRIORITY = {
    "user_upload": 0,
    "user_input": 1,
    "nas_file": 2,
    "web_search": 3,
}


def _serialize_sources(sources: list[SourcePayload]) -> str:
    # 우선순위로 정렬하되 동순위 내 원래 순서는 유지(stable sort).
    ordered = sorted(
        sources, key=lambda s: _SOURCE_KIND_PRIORITY.get(s.kind, 99)
    )
    return json.dumps(
        [
            {
                "source_id": s.source_id,
                "kind": s.kind,
                "excerpt": s.excerpt[:1500],  # 청크당 1500자 컷 (토큰 비용 관리)
                "file_path": s.file_path,
            }
            for s in ordered
        ],
        ensure_ascii=False,
    )


def _coerce_mapping(raw: dict) -> MappingResult | None:
    """LLM 응답 매핑 1건을 정규화. variable_key 누락이면 None 반환(폐기)."""
    variable_key = raw.get("variable_key")
    if not isinstance(variable_key, str) or not variable_key.strip():
        return None
    value = raw.get("value")
    if value is not None and not isinstance(value, (str, int, float, list, dict)):
        value = str(value)
    if isinstance(value, (int, float)):
        value = str(value)
    if isinstance(value, (list, dict)):
        # table_row 등 복합 값은 JSON 직렬화해 텍스트로 저장.
        value = json.dumps(value, ensure_ascii=False)
    source_id = raw.get("source_id")
    if source_id is not None:
        source_id = str(source_id)
    excerpt = raw.get("source_excerpt")
    if excerpt is not None:
        excerpt = str(excerpt)[:500]  # 발췌문 500자 제한
    try:
        confidence = float(raw.get("llm_confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    reasoning = str(raw.get("reasoning") or "").strip()
    return MappingResult(
        variable_key=variable_key.strip(),
        value=value,
        source_id=source_id,
        source_excerpt=excerpt,
        llm_confidence=confidence,
        reasoning=reasoning,
    )


def _parse_mapping_response(raw_text: str) -> list[MappingResult]:
    """Claude 응답을 MappingResult 리스트로 파싱."""
    parsed = guardrails.parse_strict_json(raw_text)
    raw_mappings = parsed.get("mappings")
    if not isinstance(raw_mappings, list):
        raise ValueError("응답 JSON에 'mappings' 배열이 없음")
    out: list[MappingResult] = []
    for raw in raw_mappings:
        if not isinstance(raw, dict):
            continue
        coerced = _coerce_mapping(raw)
        if coerced is not None:
            out.append(coerced)
    return out


def _apply_guardrails(
    parsed: list[MappingResult],
    *,
    valid_source_ids: set[str],
) -> tuple[list[MappingResult], list[MappingResult]]:
    """파싱된 매핑에 NFR-04 가드레일 5개 방어선 (코드 영역 #2/#3/#5) 적용."""
    # guardrails.sanitize_mappings 는 dict 입력이라 1회 변환.
    raw_dicts = [
        {
            "variable_key": m.variable_key,
            "value": m.value,
            "source_id": m.source_id,
            "source_excerpt": m.source_excerpt,
            "llm_confidence": m.llm_confidence,
            "reasoning": m.reasoning,
        }
        for m in parsed
    ]
    accepted_dicts, rejected_dicts = guardrails.sanitize_mappings(
        raw_dicts,
        valid_source_ids=valid_source_ids,
        threshold=settings.form_filler_min_confidence,
    )
    accepted = [_dict_to_result(d, rejected_reason=None) for d in accepted_dicts]
    rejected = [
        _dict_to_result(d, rejected_reason=d.get("_guardrail_reason"))
        for d in rejected_dicts
    ]
    return accepted, rejected


def _dict_to_result(d: dict, *, rejected_reason: str | None) -> MappingResult:
    return MappingResult(
        variable_key=d.get("variable_key", ""),
        value=d.get("value"),
        source_id=d.get("source_id"),
        source_excerpt=d.get("source_excerpt"),
        llm_confidence=float(d.get("llm_confidence", 0.0)),
        reasoning=d.get("reasoning", ""),
        rejected_reason=rejected_reason,
    )


def map_sources_to_variables(
    *,
    template_markdown: str,
    variables: list[VariablePayload],
    sources: list[SourcePayload],
    job_metadata: dict | None = None,
) -> MappingRunResult:
    """자료 청크와 양식 변수를 받아 매핑 결과를 반환.

    Args:
        template_markdown: 양식 본문 markdown (캐시 대상, system+양식이 cache 단위)
        variables: 양식 변수 목록
        sources: 자료 청크 목록 (form_data_sources에 등록된 source_id 들)
        job_metadata: Langfuse 트레이스 메타 (job_id 등)

    Returns:
        MappingRunResult — accepted/rejected/llm_response

    Raises:
        ValueError: LLM 응답 JSON 파싱 실패
        RuntimeError: API 키 없음 등 환경 문제
    """
    if not variables:
        raise ValueError("매핑할 변수가 없습니다")
    if not sources:
        # 자료 0건이면 LLM 호출 없이 모두 누락 보강 큐로.
        rejected = [
            MappingResult(
                variable_key=v.key,
                value=None,
                source_id=None,
                source_excerpt=None,
                llm_confidence=0.0,
                reasoning="",
                rejected_reason="자료가 없어 매핑 불가능 — 누락 보강 큐",
            )
            for v in variables
        ]
        # LLM 응답이 없으니 최소 메타로 응답.
        empty_response = LLMResponse(
            text="", input_tokens=0, output_tokens=0,
            cache_read_tokens=0, cache_creation_tokens=0,
            model=settings.form_filler_sonnet_model, trace_id=None, cost_usd=0.0,
        )
        return MappingRunResult(accepted=[], rejected=rejected, llm_response=empty_response)

    # system 프롬프트는 매핑 규칙 + 가드레일 (캐시 대상).
    # user 메시지에 양식 markdown + 변수 목록 + 자료 청크 모두 포함.
    variables_json = _serialize_variables(variables)
    sources_json = _serialize_sources(sources)
    system, messages = prompts.render_map_messages(variables_json, sources_json)
    # 양식 본문을 system에 추가해 양식 단위 캐싱 (PRD 6.3.2: 양식이 캐시 대상).
    extended_system = (
        f"{system}\n\n[양식 본문 markdown]\n{template_markdown[:8000]}"
    )

    llm_response = call_claude(
        system_prompt=extended_system,
        messages=messages,
        model=settings.form_filler_sonnet_model,
        max_tokens=8192,
        temperature=0,  # 소스→변수 매핑은 결정적 추출 — 값 흔들림 방지
        cache_system=True,
        cache_user_first=False,
        trace_name="form_filler.map_sources",
        trace_metadata=job_metadata or {},
    )

    parsed_mappings = _parse_mapping_response(llm_response.text)
    valid_source_ids = {s.source_id for s in sources}
    accepted, rejected = _apply_guardrails(
        parsed_mappings, valid_source_ids=valid_source_ids
    )

    # 미매핑 변수도 누락 보강 큐로 추가 (LLM이 누락한 경우).
    matched_keys = {m.variable_key for m in accepted} | {m.variable_key for m in rejected}
    for v in variables:
        if v.key in matched_keys:
            continue
        rejected.append(
            MappingResult(
                variable_key=v.key,
                value=None,
                source_id=None,
                source_excerpt=None,
                llm_confidence=0.0,
                reasoning="",
                rejected_reason="LLM이 매핑하지 않음 — 누락 보강 큐",
            )
        )

    logger.info(
        "매핑 완료: accepted=%d rejected=%d cost=$%.4f trace=%s",
        len(accepted), len(rejected), llm_response.cost_usd, llm_response.trace_id,
    )
    return MappingRunResult(accepted=accepted, rejected=rejected, llm_response=llm_response)


def regenerate_one_variable(
    *,
    variable: VariablePayload,
    user_feedback: str,
    sources: list[SourcePayload],
    valid_source_ids: set[str] | None = None,
    job_metadata: dict | None = None,
) -> tuple[MappingResult, LLMResponse]:
    """단일 변수 재생성 (FR-08, Haiku 4.5).

    사용자 피드백을 반영해 1개 변수만 다시 매핑. 전체 재호출 대비 비용 90% 감소.
    """
    variable_json = json.dumps(
        {"key": variable.key, "label": variable.label, "type": variable.type},
        ensure_ascii=False,
    )
    sources_json = _serialize_sources(sources)
    system, messages = prompts.render_regenerate_messages(
        variable_json, user_feedback, sources_json
    )
    llm_response = call_claude(
        system_prompt=system,
        messages=messages,
        model=settings.form_filler_haiku_model,
        max_tokens=2048,
        temperature=0,  # 단일 변수 재추출도 결정적
        cache_system=True,
        cache_user_first=False,
        trace_name="form_filler.regenerate_one",
        trace_metadata=job_metadata or {},
    )

    parsed = guardrails.parse_strict_json(llm_response.text)
    coerced = _coerce_mapping(parsed)
    if coerced is None:
        raise ValueError("재생성 응답에 variable_key 누락")

    whitelist = valid_source_ids if valid_source_ids is not None else {
        s.source_id for s in sources
    }
    accepted, rejected = _apply_guardrails([coerced], valid_source_ids=whitelist)
    if accepted:
        return accepted[0], llm_response
    if rejected:
        return rejected[0], llm_response
    # 가드레일이 빈 결과를 반환하는 일은 없지만 안전 폴백.
    return coerced, llm_response
