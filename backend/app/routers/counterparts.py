"""거래처(Counterpart) CRUD + 통합/매칭 라우터.

엔드포인트:
| 메서드 | 경로                                | 권한          | 비고                          |
|--------|-------------------------------------|---------------|-------------------------------|
| GET    | /api/counterparts                   | finance 모듈  | q/page/page_size/category_id  |
| GET    | /api/counterparts/{id}              | finance 모듈  | 단건                          |
| POST   | /api/counterparts                   | admin         | name/사업자번호 중복 검사     |
| PATCH  | /api/counterparts/{id}              | admin         | 모든 필드 옵션                |
| DELETE | /api/counterparts/{id}              | admin         | 트랜잭션 FK SET NULL          |
| POST   | /api/counterparts/merge             | admin         | source → target 흡수          |
| POST   | /api/counterparts/match             | finance 모듈  | 자동 매칭(읽기 전용)          |

설계 메모:
- 검색 우선순위(서버 정렬): business_no 일치 > name 정확 > alias 정확 > name ILIKE > alias ILIKE.
  → 동일 페이지 내 결과 정렬을 위해 case 식으로 가중치 부여.
- aliases 는 ARRAY(String). PG 컨테인먼트 검색은 ANY() / array_to_string + ILIKE 조합 사용.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.models.counterpart import Counterpart
from app.modules.constants import Module
from app.schemas.counterpart import (
    CounterpartCreate,
    CounterpartList,
    CounterpartMatchRequest,
    CounterpartMatchResponse,
    CounterpartMergeRequest,
    CounterpartRead,
    CounterpartUpdate,
)
from app.services.counterparts import match_counterpart, merge_counterparts

router = APIRouter(
    prefix="/api/counterparts",
    tags=["counterparts"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# GET / — 목록 (검색 + 페이지네이션)
# ---------------------------------------------------------------------------


@router.get("", response_model=CounterpartList)
async def list_counterparts(
    q: str | None = Query(default=None, description="이름/별칭/사업자번호 검색어"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    category_id: uuid.UUID | None = Query(
        default=None, description="default_category_id 필터"
    ),
    db: AsyncSession = Depends(get_db),
) -> CounterpartList:
    stmt = select(Counterpart)
    count_stmt = select(func.count()).select_from(Counterpart)

    if category_id is not None:
        stmt = stmt.where(Counterpart.default_category_id == category_id)
        count_stmt = count_stmt.where(
            Counterpart.default_category_id == category_id
        )

    if q:
        cleaned = q.strip()
        if cleaned:
            like = f"%{cleaned}%"
            # ARRAY(String) → text 캐스팅 후 ILIKE 로 부분일치 검색.
            # 정확 일치는 ARRAY.any(value) 로 PG: value = ANY(aliases) 활용.
            alias_text = cast(Counterpart.aliases, String)
            cond = or_(
                Counterpart.business_registration_no == cleaned,
                Counterpart.name == cleaned,
                Counterpart.aliases.any(cleaned),
                Counterpart.name.ilike(like),
                alias_text.ilike(like),
            )
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

            # 우선순위 정렬: 정확 매치 우선, 그 다음 ILIKE 결과.
            priority = case(
                (Counterpart.business_registration_no == cleaned, 0),
                (Counterpart.name == cleaned, 1),
                (Counterpart.aliases.any(cleaned), 2),
                (Counterpart.name.ilike(like), 3),
                else_=4,
            )
            stmt = stmt.order_by(priority.asc(), Counterpart.name.asc())
        else:
            stmt = stmt.order_by(Counterpart.name.asc())
    else:
        stmt = stmt.order_by(Counterpart.name.asc())

    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)

    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    items = [CounterpartRead.model_validate(r) for r in rows]
    return CounterpartList(
        items=items, total=total, page=page, page_size=page_size
    )


# ---------------------------------------------------------------------------
# GET /{id}
# ---------------------------------------------------------------------------


@router.get("/{counterpart_id}", response_model=CounterpartRead)
async def get_counterpart(
    counterpart_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CounterpartRead:
    row = await db.get(Counterpart, counterpart_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="거래처를 찾을 수 없습니다",
        )
    return CounterpartRead.model_validate(row)


# ---------------------------------------------------------------------------
# POST / — 신규 등록 (admin)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CounterpartRead,
    status_code=status.HTTP_201_CREATED,
    # 생성은 금융팀 member 도 가능(라우터의 require_module(FINANCE) 게이트로 충분).
    # 수정(PATCH)/삭제(DELETE)는 마스터데이터 보호를 위해 admin 유지.
)
async def create_counterpart(
    body: CounterpartCreate,
    db: AsyncSession = Depends(get_db),
) -> CounterpartRead:
    """거래처 등록.

    중복 정책:
        - name 동일 거래처 존재 시 409.
        - business_registration_no 동일 시 409 (NULL 은 허용/중복 무시).
    """
    cleaned_name = body.name.strip()
    if not cleaned_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="거래처명은 비울 수 없습니다",
        )

    dup = await db.execute(
        select(Counterpart.id).where(Counterpart.name == cleaned_name)
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="동일한 이름의 거래처가 이미 있습니다",
        )

    if body.business_registration_no:
        dup = await db.execute(
            select(Counterpart.id).where(
                Counterpart.business_registration_no
                == body.business_registration_no
            )
        )
        if dup.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="동일한 사업자번호의 거래처가 이미 있습니다",
            )

    row = Counterpart(
        id=uuid.uuid4(),
        name=cleaned_name,
        aliases=_normalize_aliases(body.aliases),
        business_registration_no=body.business_registration_no,
        default_category_id=body.default_category_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CounterpartRead.model_validate(row)


# ---------------------------------------------------------------------------
# PATCH /{id} — 수정 (admin)
# ---------------------------------------------------------------------------


@router.patch(
    "/{counterpart_id}",
    response_model=CounterpartRead,
    dependencies=[Depends(require_admin)],
)
async def update_counterpart(
    counterpart_id: uuid.UUID,
    body: CounterpartUpdate,
    db: AsyncSession = Depends(get_db),
) -> CounterpartRead:
    row = await db.get(Counterpart, counterpart_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="거래처를 찾을 수 없습니다",
        )

    payload = body.model_dump(exclude_unset=True)

    if "name" in payload:
        new_name = (payload["name"] or "").strip()
        if not new_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="거래처명은 비울 수 없습니다",
            )
        if new_name != row.name:
            dup = await db.execute(
                select(Counterpart.id).where(
                    Counterpart.name == new_name,
                    Counterpart.id != counterpart_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="동일한 이름의 거래처가 이미 있습니다",
                )
        row.name = new_name

    if "business_registration_no" in payload:
        new_brn = payload["business_registration_no"]
        if new_brn and new_brn != row.business_registration_no:
            dup = await db.execute(
                select(Counterpart.id).where(
                    Counterpart.business_registration_no == new_brn,
                    Counterpart.id != counterpart_id,
                )
            )
            if dup.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="동일한 사업자번호의 거래처가 이미 있습니다",
                )
        row.business_registration_no = new_brn

    if "aliases" in payload:
        row.aliases = _normalize_aliases(payload["aliases"])

    if "default_category_id" in payload:
        row.default_category_id = payload["default_category_id"]

    await db.commit()
    await db.refresh(row)
    return CounterpartRead.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /{id} — 삭제 (admin)
# ---------------------------------------------------------------------------


@router.delete(
    "/{counterpart_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_counterpart(
    counterpart_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """거래처 삭제. Transaction.counterpart_id 는 DB ON DELETE SET NULL."""
    row = await db.get(Counterpart, counterpart_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="거래처를 찾을 수 없습니다",
        )
    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /merge — 거래처 통합 (admin)
# ---------------------------------------------------------------------------


@router.post(
    "/merge",
    response_model=CounterpartRead,
    dependencies=[Depends(require_admin)],
)
async def merge_endpoint(
    body: CounterpartMergeRequest,
    db: AsyncSession = Depends(get_db),
) -> CounterpartRead:
    """source 거래처를 target 으로 흡수.

    영향:
        - source 의 모든 transactions.counterpart_id → target 으로 이전.
        - source.aliases + source.name → target.aliases (중복 제거).
        - source 삭제.
    """
    try:
        target = await merge_counterparts(db, body.source_id, body.target_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    await db.commit()
    await db.refresh(target)
    return CounterpartRead.model_validate(target)


# ---------------------------------------------------------------------------
# POST /match — 자동 매칭 조회
# ---------------------------------------------------------------------------


@router.post("/match", response_model=CounterpartMatchResponse)
async def match_endpoint(
    body: CounterpartMatchRequest,
    db: AsyncSession = Depends(get_db),
) -> CounterpartMatchResponse:
    """거래내역에서 거래처 마스터로 매핑할 때 사용.

    매칭 우선순위: 사업자번호 > name > alias.
    None 이면 신규 등록 후보로 처리하라는 신호.
    """
    cid, match_type = await match_counterpart(
        db, body.name, body.business_registration_no
    )
    return CounterpartMatchResponse(counterpart_id=cid, match_type=match_type)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _normalize_aliases(values: list[str] | None) -> list[str] | None:
    """빈 리스트/공백 항목 제거. 모두 비면 None 으로 정규화."""
    if not values:
        return None
    cleaned: list[str] = []
    seen: set[str] = set()
    for v in values:
        s = (v or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
    return cleaned or None
