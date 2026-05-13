import api from "./client";

/**
 * 거래 카테고리(계정과목 트리) API 클라이언트 (재무 모듈 강화 Wave 3 — FE-D).
 *
 * 백엔드: `app/routers/categories.py` (BE-C 작업 결과)
 * 트리 최대 depth 3. flat=true 시 평탄 배열, false 시 children 포함 트리.
 */

export interface CategoryRead {
  id: string;
  name: string;
  parent_id: string | null;
  code: string | null;
  color: string | null;
  depth?: number;
  created_at?: string;
  updated_at?: string | null;
}

export interface CategoryNode extends CategoryRead {
  children: CategoryNode[];
}

export interface CategoryCreate {
  name: string;
  parent_id?: string | null;
  code?: string | null;
  color?: string | null;
}

export interface CategoryUpdate {
  name?: string;
  parent_id?: string | null;
  code?: string | null;
  color?: string | null;
}

/** 트리(children 포함) 또는 평탄 목록 조회. */
export async function listCategoriesTree(): Promise<CategoryNode[]> {
  const res = await api.get<CategoryNode[]>("/api/categories", {
    params: { flat: false },
  });
  return res.data;
}

export async function listCategoriesFlat(): Promise<CategoryRead[]> {
  const res = await api.get<CategoryRead[]>("/api/categories", {
    params: { flat: true },
  });
  return res.data;
}

export async function createCategory(
  body: CategoryCreate,
): Promise<CategoryRead> {
  const res = await api.post<CategoryRead>("/api/categories", body);
  return res.data;
}

export async function updateCategory(
  id: string,
  body: CategoryUpdate,
): Promise<CategoryRead> {
  const res = await api.patch<CategoryRead>(`/api/categories/${id}`, body);
  return res.data;
}

export async function deleteCategory(id: string): Promise<void> {
  await api.delete(`/api/categories/${id}`);
}
