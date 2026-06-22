import { useCallback, useEffect, useMemo, useState } from "react";
import { message } from "antd";
import {
  DISTRIBUTION_COMPANIES,
  listProducts,
  type ProductOut,
} from "../../../api/distribution";
import { extractErrorDetail } from "../../../utils/errorUtils";
import type { CompanyChoice } from "./types";

// 전체 데이터 1회 적재 상한. 회사별 비교 카드(항상 4 업체 전수 집계)와
// 브랜드/카테고리 필터 옵션이 전체 데이터를 필요로 하므로 서버 페이지네이션
// 대신 상한을 두고, 상한 도달 시 사용자에게 "표시 N건" 경고를 노출한다.
// (전수 서버 페이지네이션은 집계 카드 UX를 깨므로 이번 패스에서는 보류.)
export const PRODUCTS_FETCH_LIMIT = 5000;

export interface CompanyStat {
  label: string;
  count: number;
  totalPurchaseQty: number;
  totalStockQty: number;
  totalVnInventoryMoveQty: number;
  totalVnSalesCompletedQty: number;
  totalVnLocalStockQty: number;
  totalPurchasePrice: number;
}

export interface GrandTotal {
  count: number;
  totalPurchaseQty: number;
  totalStockQty: number;
  totalVnInventoryMoveQty: number;
  totalVnSalesCompletedQty: number;
  totalVnLocalStockQty: number;
  totalPurchasePrice: number;
}

export interface BrandStat {
  brand: string;
  count: number;
  totalPurchaseQty: number;
  totalStockQty: number;
  totalVnInventoryMoveQty: number;
  totalVnSalesCompletedQty: number;
  totalVnLocalStockQty: number;
}

export interface FilterOption {
  value: string;
  label: string;
}

export interface UseProductsResult {
  data: ProductOut[];
  loading: boolean;
  capped: boolean;
  fetchData: () => Promise<void>;
  company: CompanyChoice;
  setCompany: (v: CompanyChoice) => void;
  brandFilter: string;
  setBrandFilter: (v: string) => void;
  categoryFilter: string;
  setCategoryFilter: (v: string) => void;
  searchInput: string;
  setSearchInput: (v: string) => void;
  companyStats: CompanyStat[];
  grandTotal: GrandTotal;
  brandOptions: FilterOption[];
  categoryOptions: FilterOption[];
  brandStats: BrandStat[];
  filtered: ProductOut[];
}

export function useProducts(): UseProductsResult {
  const [data, setData] = useState<ProductOut[]>([]);
  const [loading, setLoading] = useState(false);
  // fetch 결과가 상한과 같으면 잘렸을 수 있다는 신호.
  const [capped, setCapped] = useState(false);

  const [company, setCompany] = useState<CompanyChoice>("all");
  const [brandFilter, setBrandFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState("");

  // 회사별 비교 카드를 위해 전체 데이터 1회 fetch — 회사 필터는 클라이언트.
  // 상한(PRODUCTS_FETCH_LIMIT) 도달 시 일부만 표시될 수 있어 capped 플래그로 안내.
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listProducts({ limit: PRODUCTS_FETCH_LIMIT });
      setData(items);
      setCapped(items.length >= PRODUCTS_FETCH_LIMIT);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "명품재고 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  // 회사 필터 적용된 데이터 — 통계·테이블 모두 이 컨텍스트 기준.
  const companyScoped = useMemo(() => {
    if (company === "all") return data;
    return data.filter((p) => p.company_label === company);
  }, [data, company]);

  // 회사별 비교 — 항상 전체 데이터 기준 4 회사 row (0이어도 표시).
  const companyStats = useMemo(() => {
    const map = new Map<
      string,
      {
        count: number;
        totalPurchaseQty: number;
        totalStockQty: number;
        totalVnInventoryMoveQty: number;
        totalVnSalesCompletedQty: number;
        totalVnLocalStockQty: number;
        totalPurchasePrice: number;
      }
    >();
    for (const company of DISTRIBUTION_COMPANIES) {
      map.set(company, {
        count: 0,
        totalPurchaseQty: 0,
        totalStockQty: 0,
        totalVnInventoryMoveQty: 0,
        totalVnSalesCompletedQty: 0,
        totalVnLocalStockQty: 0,
        totalPurchasePrice: 0,
      });
    }
    for (const p of data) {
      const key = p.company_label ?? "(미지정)";
      const prev = map.get(key) ?? {
        count: 0,
        totalPurchaseQty: 0,
        totalStockQty: 0,
        totalVnInventoryMoveQty: 0,
        totalVnSalesCompletedQty: 0,
        totalVnLocalStockQty: 0,
        totalPurchasePrice: 0,
      };
      const price = p.purchase_price ? Number(p.purchase_price) || 0 : 0;
      map.set(key, {
        count: prev.count + 1,
        totalPurchaseQty: prev.totalPurchaseQty + (p.purchase_qty ?? 0),
        totalStockQty: prev.totalStockQty + (p.domestic_stock_qty ?? 0),
        totalVnInventoryMoveQty:
          prev.totalVnInventoryMoveQty + (p.vn_inventory_move_qty ?? 0),
        totalVnSalesCompletedQty:
          prev.totalVnSalesCompletedQty + (p.vn_sales_completed_qty ?? 0),
        totalVnLocalStockQty:
          prev.totalVnLocalStockQty + (p.vn_local_stock_qty ?? 0),
        totalPurchasePrice: prev.totalPurchasePrice + price,
      });
    }
    return Array.from(map.entries()).map(([label, stats]) => ({
      label,
      ...stats,
    }));
  }, [data]);

  // 전체 총합 (현재 회사 컨텍스트 기준) — 페이지 상단 KPI 카드.
  const grandTotal = useMemo(() => {
    let count = 0;
    let totalPurchaseQty = 0;
    let totalStockQty = 0;
    let totalVnInventoryMoveQty = 0;
    let totalVnSalesCompletedQty = 0;
    let totalVnLocalStockQty = 0;
    let totalPurchasePrice = 0;
    for (const p of companyScoped) {
      count += 1;
      totalPurchaseQty += p.purchase_qty ?? 0;
      totalStockQty += p.domestic_stock_qty ?? 0;
      totalVnInventoryMoveQty += p.vn_inventory_move_qty ?? 0;
      totalVnSalesCompletedQty += p.vn_sales_completed_qty ?? 0;
      totalVnLocalStockQty += p.vn_local_stock_qty ?? 0;
      totalPurchasePrice += p.purchase_price ? Number(p.purchase_price) || 0 : 0;
    }
    return {
      count,
      totalPurchaseQty,
      totalStockQty,
      totalVnInventoryMoveQty,
      totalVnSalesCompletedQty,
      totalVnLocalStockQty,
      totalPurchasePrice,
    };
  }, [companyScoped]);

  // 브랜드 목록 (필터 옵션용) — 현재 회사 컨텍스트 기준.
  const brandOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of companyScoped) set.add(p.brand);
    return [
      { value: "all", label: "전체 브랜드" },
      ...Array.from(set)
        .sort()
        .map((b) => ({ value: b, label: b })),
    ];
  }, [companyScoped]);

  // 카테고리 목록 (필터 옵션용).
  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of companyScoped) {
      if (p.category) set.add(p.category);
    }
    return [
      { value: "all", label: "전체 카테고리" },
      ...Array.from(set)
        .sort()
        .map((c) => ({ value: c, label: c })),
    ];
  }, [companyScoped]);

  // 브랜드별 그룹 통계 (현재 회사 컨텍스트 기준 — 검색/카테고리 필터 적용 전).
  const brandStats = useMemo(() => {
    const map = new Map<
      string,
      {
        count: number;
        totalPurchaseQty: number;
        totalStockQty: number;
        totalVnInventoryMoveQty: number;
        totalVnSalesCompletedQty: number;
        totalVnLocalStockQty: number;
      }
    >();
    for (const p of companyScoped) {
      const prev = map.get(p.brand) ?? {
        count: 0,
        totalPurchaseQty: 0,
        totalStockQty: 0,
        totalVnInventoryMoveQty: 0,
        totalVnSalesCompletedQty: 0,
        totalVnLocalStockQty: 0,
      };
      map.set(p.brand, {
        count: prev.count + 1,
        totalPurchaseQty: prev.totalPurchaseQty + (p.purchase_qty ?? 0),
        totalStockQty: prev.totalStockQty + (p.domestic_stock_qty ?? 0),
        totalVnInventoryMoveQty:
          prev.totalVnInventoryMoveQty + (p.vn_inventory_move_qty ?? 0),
        totalVnSalesCompletedQty:
          prev.totalVnSalesCompletedQty + (p.vn_sales_completed_qty ?? 0),
        totalVnLocalStockQty:
          prev.totalVnLocalStockQty + (p.vn_local_stock_qty ?? 0),
      });
    }
    return Array.from(map.entries())
      .map(([brand, stats]) => ({ brand, ...stats }))
      .sort((a, b) => b.totalStockQty - a.totalStockQty);
  }, [companyScoped]);

  // 테이블 표시용 — 회사 + 브랜드 + 카테고리 + 검색 모두 적용.
  const filtered = useMemo(() => {
    const q = searchInput.trim().toLowerCase();
    return companyScoped.filter((p) => {
      if (brandFilter !== "all" && p.brand !== brandFilter) return false;
      if (categoryFilter !== "all" && p.category !== categoryFilter)
        return false;
      if (q) {
        const haystack = [p.product_name_en ?? "", p.product_code ?? ""]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [companyScoped, brandFilter, categoryFilter, searchInput]);

  return {
    data,
    loading,
    capped,
    fetchData,
    company,
    setCompany,
    brandFilter,
    setBrandFilter,
    categoryFilter,
    setCategoryFilter,
    searchInput,
    setSearchInput,
    companyStats,
    grandTotal,
    brandOptions,
    categoryOptions,
    brandStats,
    filtered,
  };
}
