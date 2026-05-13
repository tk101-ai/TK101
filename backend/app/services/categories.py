"""카테고리 트리 헬퍼.

책임 분리:
- 라우터는 HTTP 직렬화/응답 코드 결정.
- 본 모듈은 트리 구성/순환 검사/depth 계산 같은 도메인 로직 보관.

설계 메모:
- build_tree: 단일 DB 라운드트립으로 받은 평탄 리스트(O(N))를 부모-자식 dict 로 재조립.
- compute_depth: 부모 depth + 1, 부모 없으면 1. 부모 미존재 시 404.
- check_circular: parent_id 체인을 따라 올라가며 자기 ID 가 나오는지 확인.
  → BFS/DFS 가 아니라 부모 체인 추적(최대 깊이 3)이라 항상 O(3) 이하.

검증 원칙:
- 모든 함수는 호출 시점에 DB 상태를 신뢰. 트랜잭션 격리는 호출자가 결정.
- ValueError 로 도메인 오류 전달 → 라우터에서 HTTPException 변환.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.schemas.category import CategoryRead, CategoryTree

# 트리 최대 깊이. DB CHECK 와 동일 값 유지.
MAX_DEPTH = 3


def build_tree(rows: list[Category]) -> list[CategoryTree]:
    """평탄 카테고리 리스트를 트리 구조(루트의 리스트)로 변환.

    Args:
        rows: 정렬 무관한 Category ORM 객체 목록.

    Returns:
        루트(parent_id is None) 카테고리들의 CategoryTree 리스트.
        각 노드의 children 은 동일 부모를 가진 자식들로 채워짐.
    """
    nodes: dict[uuid.UUID, CategoryTree] = {}
    for row in rows:
        node = CategoryTree(
            id=row.id,
            name=row.name,
            parent_id=row.parent_id,
            code=row.code,
            color=row.color,
            depth=row.depth,
            created_at=row.created_at,
            updated_at=row.updated_at,
            children=[],
        )
        nodes[row.id] = node

    roots: list[CategoryTree] = []
    for row in rows:
        node = nodes[row.id]
        if row.parent_id is None:
            roots.append(node)
            continue
        parent = nodes.get(row.parent_id)
        if parent is None:
            # 부모가 같은 결과셋에 없으면 루트로 승격 (예: 부분 조회).
            roots.append(node)
        else:
            parent.children.append(node)

    return roots


def to_flat(rows: list[Category]) -> list[CategoryRead]:
    """ORM 행 목록을 CategoryRead 리스트로 직렬화."""
    return [CategoryRead.model_validate(r) for r in rows]


async def compute_depth(
    db: AsyncSession, parent_id: uuid.UUID | None
) -> int:
    """parent_id 기반 depth 계산.

    Raises:
        ValueError: 부모를 찾을 수 없거나, 부모 depth 가 이미 MAX_DEPTH 일 때.
    """
    if parent_id is None:
        return 1

    result = await db.execute(
        select(Category.depth).where(Category.id == parent_id)
    )
    parent_depth = result.scalar_one_or_none()
    if parent_depth is None:
        raise ValueError("상위 카테고리를 찾을 수 없습니다")
    new_depth = parent_depth + 1
    if new_depth > MAX_DEPTH:
        raise ValueError(
            f"카테고리 최대 깊이({MAX_DEPTH}단)를 초과합니다"
        )
    return new_depth


async def check_circular(
    db: AsyncSession,
    category_id: uuid.UUID,
    new_parent_id: uuid.UUID,
) -> None:
    """자기 자신 또는 자기 후손을 부모로 지정하려는지 검사.

    부모 체인을 위로 따라가며 category_id 가 나오면 순환.

    Raises:
        ValueError: 순환 참조 감지 시.
    """
    if category_id == new_parent_id:
        raise ValueError("자기 자신을 상위 카테고리로 지정할 수 없습니다")

    current: uuid.UUID | None = new_parent_id
    # MAX_DEPTH 이상 따라갈 일은 없지만, 안전상 작은 상한.
    for _ in range(MAX_DEPTH + 2):
        if current is None:
            return
        if current == category_id:
            raise ValueError(
                "하위 카테고리를 상위 카테고리로 지정할 수 없습니다 (순환 참조)"
            )
        result = await db.execute(
            select(Category.parent_id).where(Category.id == current)
        )
        current = result.scalar_one_or_none()
    # 비정상적으로 깊은 체인 — 데이터 무결성 경보 영역.
    raise ValueError("카테고리 부모 체인이 비정상적으로 깊습니다")
