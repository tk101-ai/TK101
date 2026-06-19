"""카테고리 CRUD 라우터 — 비용 분류 트리 (max depth=3).

엔드포인트:
| 메서드 | 경로                              | 권한            | 비고                          |
|--------|-----------------------------------|-----------------|-------------------------------|
| GET    | /api/categories?flat=true|false   | finance 모듈    | 기본 tree, flat=true 시 평탄  |
| GET    | /api/categories/{id}              | finance 모듈    | 단건                          |
| POST   | /api/categories                   | admin           | depth 자동 계산               |
| PATCH  | /api/categories/{id}              | admin           | parent 변경 시 순환검사 + 재계산 |
| DELETE | /api/categories/{id}              | admin           | 자식 있으면 400               |

연관 동작:
- DELETE: 트랜잭션 FK 는 ON DELETE SET NULL (DB 레벨).
- 자식 카테고리가 남아 있으면 400 으로 거부 → 운영자가 먼저 재배치 결정.
  (자식까지 자동 분리하지 않는 이유: 회계 분류는 사용자의 의도가 필요)
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.models.category import Category
from app.modules.constants import Module
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryTree,
    CategoryUpdate,
)
from app.services.categories import (
    build_tree,
    check_circular,
    compute_depth,
    to_flat,
)

router = APIRouter(
    prefix="/api/categories",
    tags=["categories"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# GET / — 목록 (트리 or 평탄)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CategoryTree] | list[CategoryRead])
async def list_categories(
    flat: bool = Query(default=False, description="true 면 평탄 리스트, false 면 트리"),
    db: AsyncSession = Depends(get_db),
):
    """카테고리 목록.

    기본 트리 응답. flat=true 면 단순 리스트로 반환.
    정렬: depth 오름차순, 같은 depth 내 name.
    """
    stmt = select(Category).order_by(Category.depth.asc(), Category.name.asc())
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    if flat:
        return to_flat(rows)
    return build_tree(rows)


# ---------------------------------------------------------------------------
# GET /{id}
# ---------------------------------------------------------------------------


@router.get("/{category_id}", response_model=CategoryRead)
async def get_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    row = await db.get(Category, category_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="카테고리를 찾을 수 없습니다",
        )
    return CategoryRead.model_validate(row)


# ---------------------------------------------------------------------------
# POST / — 신규 등록 (admin)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
    # 생성은 금융팀 member 도 가능(라우터의 require_module(FINANCE) 게이트로 충분).
    # 수정(PATCH)/삭제(DELETE)는 마스터데이터 보호를 위해 admin 유지.
)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    """카테고리 신규 등록. depth 는 서버 계산."""
    try:
        depth = await compute_depth(db, body.parent_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if body.code:
        result = await db.execute(
            select(Category.id).where(Category.code == body.code)
        )
        if result.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 사용 중인 코드입니다",
            )

    row = Category(
        id=uuid.uuid4(),
        name=body.name,
        parent_id=body.parent_id,
        code=body.code,
        color=body.color,
        depth=depth,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return CategoryRead.model_validate(row)


# ---------------------------------------------------------------------------
# PATCH /{id} — 수정 (admin)
# ---------------------------------------------------------------------------


@router.patch(
    "/{category_id}",
    response_model=CategoryRead,
    dependencies=[Depends(require_admin)],
)
async def update_category(
    category_id: uuid.UUID,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
) -> CategoryRead:
    row = await db.get(Category, category_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="카테고리를 찾을 수 없습니다",
        )

    payload = body.model_dump(exclude_unset=True)

    # parent_id 변경 시 순환 검사 + depth 재계산.
    if "parent_id" in payload:
        new_parent_id = payload["parent_id"]
        if new_parent_id is not None:
            try:
                await check_circular(db, category_id, new_parent_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
                ) from exc
        try:
            new_depth = await compute_depth(db, new_parent_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

        # 부모 변경으로 자식들의 depth 도 올라가지 않는지 사전 검증.
        max_child_depth = await _max_descendant_depth(db, category_id)
        delta = new_depth - row.depth
        if max_child_depth + delta > 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="하위 카테고리 포함 최대 깊이(3단)를 초과합니다",
            )

        row.parent_id = new_parent_id
        row.depth = new_depth
        # 자손들의 depth 도 함께 보정.
        if delta != 0:
            await _shift_descendant_depth(db, category_id, delta)

    if "code" in payload and payload["code"] != row.code:
        new_code = payload["code"]
        if new_code:
            result = await db.execute(
                select(Category.id).where(
                    Category.code == new_code, Category.id != category_id
                )
            )
            if result.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="이미 사용 중인 코드입니다",
                )
        row.code = new_code

    if "name" in payload:
        row.name = payload["name"]
    if "color" in payload:
        row.color = payload["color"]

    await db.commit()
    await db.refresh(row)
    return CategoryRead.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /{id} — 삭제 (admin)
# ---------------------------------------------------------------------------


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_admin)],
)
async def delete_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """카테고리 삭제.

    - 자식 카테고리가 남아 있으면 400 (운영자가 재배치 필요).
    - Transaction.category_id 는 DB 레벨 ON DELETE SET NULL 로 자동 NULL.
    - Counterpart.default_category_id 도 SET NULL.
    """
    row = await db.get(Category, category_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="카테고리를 찾을 수 없습니다",
        )

    result = await db.execute(
        select(Category.id).where(Category.parent_id == category_id).limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="하위 카테고리가 존재하는 카테고리는 삭제할 수 없습니다. 먼저 하위 항목을 정리하세요.",
        )

    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 자손 depth 처리
# ---------------------------------------------------------------------------


async def _max_descendant_depth(
    db: AsyncSession, root_id: uuid.UUID
) -> int:
    """root_id 이하 자손의 최대 depth (root 자신 포함)."""
    root = await db.get(Category, root_id)
    if root is None:
        return 0
    max_depth = root.depth
    stack: list[uuid.UUID] = [root_id]
    while stack:
        cur = stack.pop()
        result = await db.execute(
            select(Category).where(Category.parent_id == cur)
        )
        for child in result.scalars().all():
            if child.depth > max_depth:
                max_depth = child.depth
            stack.append(child.id)
    return max_depth


async def _shift_descendant_depth(
    db: AsyncSession, root_id: uuid.UUID, delta: int
) -> None:
    """root_id 의 모든 자손 depth 에 delta 더하기 (root 본인 제외)."""
    if delta == 0:
        return
    stack: list[uuid.UUID] = [root_id]
    while stack:
        cur = stack.pop()
        result = await db.execute(
            select(Category).where(Category.parent_id == cur)
        )
        for child in result.scalars().all():
            child.depth = child.depth + delta
            stack.append(child.id)
