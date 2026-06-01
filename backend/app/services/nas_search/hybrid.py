"""하이브리드 검색 결합 로직 (순수 함수 — DB/네트워크 의존 없음).

두 검색 arm을 결합한다:
- 의미검색(벡터): 임베딩 cosine 유사도 순위
- 정확검색(키워드): pg_trgm ILIKE 토큰 매칭 순위

두 순위를 RRF(Reciprocal Rank Fusion)로 합쳐 최종 순위를 만든다.
RRF는 점수 스케일이 다른 두 랭킹을 '순위'만으로 안정적으로 결합하는 표준 기법.

여기 함수들은 라우터(SQL 실행)와 분리해 단위 테스트가 쉽게 한다.
"""
from __future__ import annotations

import re

# 토큰 분리 — 공백 및 일부 구분자. 대시(-)는 분리하지 않는다:
# 품번 "12865-24-008320X" 전체를 한 토큰으로 유지해 정확 ILIKE 매칭을 살리기 위함.
_TOKEN_SPLIT = re.compile(r"[\s,;/|]+")

# 토큰 양끝에서 떼어낼 따옴표/괄호류.
_TRIM_CHARS = "\"'`()[]{}<>"

# 기본 RRF 상수 — 원 논문 권장값. 클수록 상위 순위 가중이 완만해진다.
DEFAULT_RRF_K = 60

# 한 쿼리에서 사용할 최대 토큰 수. 너무 많으면 ILIKE OR 절이 비대해짐.
MAX_TERMS = 12

# 토큰 최소 길이. 단, 숫자를 포함한 짧은 토큰(연도 등)은 예외로 허용.
MIN_TERM_LEN = 2


def tokenize_query(
    query: str,
    *,
    max_terms: int = MAX_TERMS,
    min_len: int = MIN_TERM_LEN,
) -> list[str]:
    """자연어 쿼리를 키워드 arm용 토큰 리스트로 분해.

    - 소문자화(ILIKE는 대소문자 무시이지만 중복 제거 일관성 위해).
    - 공백/쉼표/슬래시 등으로 분리하되 대시는 유지(품번 보존).
    - 양끝 따옴표·괄호 제거.
    - min_len 미만 토큰은 제외하되, 숫자를 포함하면(연도·금액 등) 길이 1도 허용.
    - 등장 순서를 보존하며 중복 제거, 최대 max_terms개.
    """
    if not query:
        return []

    out: list[str] = []
    seen: set[str] = set()
    for raw in _TOKEN_SPLIT.split(query.strip().lower()):
        term = raw.strip(_TRIM_CHARS).strip()
        if not term:
            continue
        has_digit = any(ch.isdigit() for ch in term)
        if len(term) < min_len and not has_digit:
            continue
        if term in seen:
            continue
        seen.add(term)
        out.append(term)
        if len(out) >= max_terms:
            break
    return out


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    *,
    k: int = DEFAULT_RRF_K,
) -> dict[str, float]:
    """여러 순위 리스트를 RRF 점수로 결합.

    Args:
        rankings: 각 arm이 만든 '키(예: 파일 경로) 순위 리스트'들.
                  각 리스트는 상위(0번 인덱스)부터 정렬돼 있어야 한다.
        k: RRF 상수.

    Returns:
        키 → 누적 RRF 점수. 점수가 높을수록 상위.
        한 키가 여러 arm에 등장하면 점수가 합산돼 자연스럽게 상위로 올라간다.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
    return scores


def like_escape(term: str) -> str:
    """ILIKE 패턴에 안전하게 넣기 위해 와일드카드(%, _)와 escape 문자를 이스케이프.

    SQLAlchemy `.ilike(pattern, escape="\\\\")`와 함께 사용한다.
    이스케이프하지 않으면 사용자가 입력한 %/_ 가 와일드카드로 동작해
    의도치 않게 검색 범위가 넓어진다.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
