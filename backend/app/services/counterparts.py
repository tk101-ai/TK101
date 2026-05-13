"""거래처 매칭/통합 헬퍼.

설계 메모:
- match_counterpart: 우선순위 매칭.
    1) business_registration_no 완전 일치 (최강 신호)
    2) name 완전 일치
    3) aliases 배열 내 완전 일치 (PG: :v = ANY(aliases))
    하나도 없으면 ("none", None) 반환 → 라우터에서 신규 등록 후보 분기.
- merge_counterparts: source → target 흡수.
    * Transaction.counterpart_id source → target 일괄 UPDATE.
    * source.aliases + source.name 을 target.aliases 에 합치고 중복 제거.
    * source 삭제.
    * 호출자가 commit 책임.

오류 시 ValueError 로 도메인 메시지 전달, 라우터가 HTTPException 변환.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.counterpart import Counterpart
from app.models.transaction import Transaction
from app.schemas.counterpart import MatchType


async def match_counterpart(
    db: AsyncSession,
    name: str,
    business_no: str | None,
) -> tuple[uuid.UUID | None, MatchType]:
    """이름/사업자번호로 거래처 마스터 매칭.

    Args:
        db: 비동기 세션.
        name: 거래처 이름 (필수, 공백 trim 권장).
        business_no: 사업자등록번호 (옵션).

    Returns:
        (counterpart_id, match_type).
        match_type: "exact_business_no" | "exact_name" | "alias" | "none".

    매칭 실패 시 (None, "none"). 절대 예외 던지지 않음 — 라우터가 신규 등록 흐름 결정.
    """
    cleaned_name = name.strip()

    # 1) 사업자번호 완전 일치 — 가장 강한 신호.
    if business_no:
        result = await db.execute(
            select(Counterpart.id).where(
                Counterpart.business_registration_no == business_no
            )
        )
        cid = result.scalar_one_or_none()
        if cid is not None:
            return cid, "exact_business_no"

    if not cleaned_name:
        return None, "none"

    # 2) name 완전 일치.
    result = await db.execute(
        select(Counterpart.id).where(Counterpart.name == cleaned_name)
    )
    cid = result.scalar_one_or_none()
    if cid is not None:
        return cid, "exact_name"

    # 3) aliases 배열 내 완전 일치.
    # SQLAlchemy ARRAY.any(value): 컬럼 배열에 value 가 있는지(PG: value = ANY(column)).
    result = await db.execute(
        select(Counterpart.id).where(Counterpart.aliases.any(cleaned_name))
    )
    cid = result.scalar_one_or_none()
    if cid is not None:
        return cid, "alias"

    return None, "none"


def _dedupe_aliases(values: list[str]) -> list[str]:
    """순서 보존 중복 제거 + 공백 trim + 빈 문자열 제거."""
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = (v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


async def merge_counterparts(
    db: AsyncSession,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
) -> Counterpart:
    """source 거래처를 target 으로 흡수.

    절차:
        1) source/target 로드 — 미존재 시 ValueError.
        2) Transaction.counterpart_id source → target 일괄 UPDATE.
        3) target.aliases 에 source.name + source.aliases 합치고 중복 제거.
        4) source 삭제.

    호출자가 await db.commit() 책임. 부분 실패 시 호출자에서 rollback.
    """
    if source_id == target_id:
        raise ValueError("동일한 거래처는 통합할 수 없습니다")

    source = await db.get(Counterpart, source_id)
    if source is None:
        raise ValueError("이전(source) 거래처를 찾을 수 없습니다")
    target = await db.get(Counterpart, target_id)
    if target is None:
        raise ValueError("대상(target) 거래처를 찾을 수 없습니다")

    # 1) Transaction.counterpart_id 이전.
    await db.execute(
        update(Transaction)
        .where(Transaction.counterpart_id == source_id)
        .values(counterpart_id=target_id)
    )

    # 2) aliases 합치기. source.name 도 향후 매칭을 위해 alias 로 보존.
    merged: list[str] = []
    if target.aliases:
        merged.extend(target.aliases)
    if source.name:
        merged.append(source.name)
    if source.aliases:
        merged.extend(source.aliases)
    # 정식 이름과 동일한 alias 는 제거 (불필요).
    merged = [a for a in _dedupe_aliases(merged) if a != target.name]
    target.aliases = merged or None

    # 3) source 삭제.
    await db.delete(source)
    await db.flush()
    return target
