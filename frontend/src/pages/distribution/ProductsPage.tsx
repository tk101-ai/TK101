import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Link } from "react-router-dom";
import {
  COMPANY_FILTER_OPTIONS,
  DISTRIBUTION_COMPANIES,
  type DistributionCompany,
  listProducts,
  type ProductOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;

// ---------------------------------------------------------------------------
// 색상 매핑
// ---------------------------------------------------------------------------

const CATEGORY_COLOR: Record<string, string> = {
  Bag: "blue",
  Belts: "green",
  Ring: "gold",
  Scarf: "purple",
};

const BRAND_COLOR: Record<string, string> = {
  루이비통: "magenta",
  "LOUIS VUITTON": "magenta",
  고야드: "gold",
  GOYARD: "gold",
  Cartier: "red",
  BURBERRY: "orange",
  DIOR: "default",
};

function getCategoryColor(cat: string | null): string {
  if (!cat) return "default";
  return CATEGORY_COLOR[cat] ?? "default";
}

function getBrandColor(brand: string): string {
  if (BRAND_COLOR[brand]) return BRAND_COLOR[brand];
  const upper = brand.toUpperCase();
  for (const key of Object.keys(BRAND_COLOR)) {
    if (key.toUpperCase() === upper) return BRAND_COLOR[key];
  }
  return "default";
}

function formatAmount(value: string | null): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return n.toLocaleString("ko-KR", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
}

function formatNumber(value: number | null): string {
  if (value == null) return "—";
  return value.toLocaleString("ko-KR");
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD");
}

type CompanyChoice = DistributionCompany | "all";

// ---------------------------------------------------------------------------
// 페이지
// ---------------------------------------------------------------------------

/**
 * 명품재고대장 조회 페이지 (T9 Phase F-D).
 *
 * 백엔드: `GET /api/distribution/data/products`
 * - 회사 / 브랜드 / 카테고리 / 검색(제품명·코드) 필터
 * - 상단 브랜드별 요약 카드 (가시성 ↑: 브랜드명 큰 글씨 + 제품/재고/매입 수치)
 * - 페이지 사이즈 50
 */
export default function ProductsPage() {
  const [data, setData] = useState<ProductOut[]>([]);
  const [loading, setLoading] = useState(false);

  const [company, setCompany] = useState<CompanyChoice>("all");
  const [brandFilter, setBrandFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState("");

  // 회사별 비교 카드를 위해 전체 데이터 1회 fetch — 회사 필터는 클라이언트.
  // 4 회사 풀 적재 시 ~2000 행 가정, limit 5000 안전 마진.
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listProducts({ limit: 5000 });
      setData(items);
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

  const columns: ColumnsType<ProductOut> = [
    {
      title: "회사",
      dataIndex: "company_label",
      width: 110,
      fixed: "left",
      render: (v: string | null | undefined) =>
        v ? <Tag color="geekblue">{v}</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: "브랜드",
      dataIndex: "brand",
      width: 140,
      render: (v: string) => <Tag color={getBrandColor(v)}>{v}</Tag>,
    },
    {
      title: "제품명(영문)",
      dataIndex: "product_name_en",
      width: 240,
      render: (v: string | null) =>
        v ? <Text>{v}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: "제품코드",
      dataIndex: "product_code",
      width: 160,
      render: (v: string | null) =>
        v ? (
          <Text style={{ fontFamily: "monospace", fontSize: 12 }}>{v}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "카테고리",
      dataIndex: "category",
      width: 110,
      render: (v: string | null) =>
        v ? (
          <Tag color={getCategoryColor(v)}>{v}</Tag>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: "매입수량",
      dataIndex: "purchase_qty",
      width: 100,
      align: "right" as const,
      render: (v: number | null) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "국내재고",
      dataIndex: "domestic_stock_qty",
      width: 100,
      align: "right" as const,
      render: (v: number | null) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "VN재고이동",
      dataIndex: "vn_inventory_move_qty",
      width: 110,
      align: "right" as const,
      render: (v: number | null) => (
        <span
          style={{ fontVariantNumeric: "tabular-nums", color: "#722ed1" }}
        >
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "VN매출완료",
      dataIndex: "vn_sales_completed_qty",
      width: 110,
      align: "right" as const,
      render: (v: number | null) => (
        <span
          style={{ fontVariantNumeric: "tabular-nums", color: "#fa8c16" }}
        >
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "VN현지재고",
      dataIndex: "vn_local_stock_qty",
      width: 110,
      align: "right" as const,
      render: (v: number | null) => (
        <span
          style={{ fontVariantNumeric: "tabular-nums", color: "#13c2c2" }}
        >
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "매입금액",
      dataIndex: "purchase_price",
      width: 140,
      align: "right" as const,
      render: (v: string | null) => (
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {formatAmount(v)}
        </span>
      ),
    },
    {
      title: "매입일",
      dataIndex: "purchase_date",
      width: 110,
      render: (v: string | null) => (
        <Text style={{ fontSize: 12 }}>{formatDate(v)}</Text>
      ),
    },
    {
      title: "승인번호",
      dataIndex: "approval_number",
      width: 140,
      render: (v: string | null) =>
        v ? (
          <Text style={{ fontFamily: "monospace", fontSize: 12 }}>{v}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
  ];

  return (
    <div style={{ maxWidth: 1680 }}>
      <div
        style={{
          marginBottom: 24,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
            명품재고대장
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            업로드된 명품재고 전체 목록입니다. 회사를 선택하면 해당 회사 적재분만
            노출됩니다. 매주 업로드 시 전체 갱신됩니다.
          </Paragraph>
        </div>
        <Space wrap>
          <Select<CompanyChoice>
            value={company}
            onChange={(v) => setCompany(v)}
            options={COMPANY_FILTER_OPTIONS}
            style={{ width: 200 }}
          />
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            새로고침
          </Button>
          <Link to="/distribution/data/upload">
            <Button type="primary" icon={<CloudUploadOutlined />}>
              데이터 업로드
            </Button>
          </Link>
        </Space>
      </div>

      {/* 전체 총합 KPI — 현재 회사 컨텍스트 기준 */}
      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title={
                <Space size={4}>
                  <Text>총 제품 수</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {company === "all" ? "(전체)" : `(${company})`}
                  </Text>
                </Space>
              }
              value={grandTotal.count}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title="총 매입수량"
              value={grandTotal.totalPurchaseQty}
              suffix="개"
              valueStyle={{ color: "#1677ff" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title="총 국내재고"
              value={grandTotal.totalStockQty}
              suffix="개"
              valueStyle={{ color: "#52c41a" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title="VN 재고이동"
              value={grandTotal.totalVnInventoryMoveQty}
              suffix="개"
              valueStyle={{ color: "#722ed1" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title="VN 매출완료"
              value={grandTotal.totalVnSalesCompletedQty}
              suffix="개"
              valueStyle={{ color: "#fa8c16" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={3}>
          <Card size="small">
            <Statistic
              title="VN 현지재고"
              value={grandTotal.totalVnLocalStockQty}
              suffix="개"
              valueStyle={{ color: "#13c2c2" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={6}>
          <Card size="small">
            <Statistic
              title="총 매입금액 (KRW)"
              value={grandTotal.totalPurchasePrice}
              precision={0}
              groupSeparator=","
            />
          </Card>
        </Col>
      </Row>

      {/* 회사별 비교 — 항상 4 회사 노출 (회사 Select와 무관) */}
      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <Text strong>회사별 재고 요약</Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              (4 업체 비교 — 항상 전체 데이터 기준)
            </Text>
          </Space>
        }
      >
        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
          }}
        >
          {companyStats.map((s) => {
            const isSelected = company === s.label;
            return (
              <div
                key={s.label}
                onClick={() => setCompany(s.label as CompanyChoice)}
                style={{
                  padding: "12px 14px",
                  background: isSelected ? "#e6f4ff" : "#fafafa",
                  border: `1px solid ${isSelected ? "#1677ff" : "#f0f0f0"}`,
                  borderRadius: 8,
                  cursor: "pointer",
                  transition: "all 0.15s",
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <Text strong style={{ fontSize: 15 }}>
                    {s.label}
                  </Text>
                  <Tag color="geekblue" style={{ margin: 0 }}>
                    {s.count}건
                  </Tag>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(5, 1fr)",
                    gap: 4,
                  }}
                >
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      매입
                    </Text>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#1677ff",
                      }}
                    >
                      {formatNumber(s.totalPurchaseQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      국내
                    </Text>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#52c41a",
                      }}
                    >
                      {formatNumber(s.totalStockQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN이동
                    </Text>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#722ed1",
                      }}
                    >
                      {formatNumber(s.totalVnInventoryMoveQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN매출
                    </Text>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#fa8c16",
                      }}
                    >
                      {formatNumber(s.totalVnSalesCompletedQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN재고
                    </Text>
                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#13c2c2",
                      }}
                    >
                      {formatNumber(s.totalVnLocalStockQty)}
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* 브랜드별 요약 카드 — 현재 회사 컨텍스트 기준 */}
      {brandStats.length > 0 && (
        <Card
          size="small"
          style={{ marginBottom: 16 }}
          title={
            <Space>
              <Text strong>브랜드별 요약</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {company === "all" ? "전체 회사" : company}
              </Text>
            </Space>
          }
        >
          <div
            style={{
              display: "grid",
              gap: 12,
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            }}
          >
            {brandStats.map((s) => (
              <div
                key={s.brand}
                style={{
                  padding: "14px 16px",
                  background: "#fafafa",
                  border: "1px solid #f0f0f0",
                  borderRadius: 8,
                  display: "flex",
                  flexDirection: "column",
                  gap: 10,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                  }}
                >
                  <Text
                    strong
                    style={{
                      fontSize: 18,
                      letterSpacing: "-0.02em",
                      lineHeight: 1.2,
                    }}
                  >
                    {s.brand}
                  </Text>
                  <Tag color={getBrandColor(s.brand)} style={{ margin: 0 }}>
                    {s.count}개
                  </Tag>
                </div>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(5, 1fr)",
                    gap: 6,
                  }}
                >
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      매입
                    </Text>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#1677ff",
                      }}
                    >
                      {formatNumber(s.totalPurchaseQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      국내
                    </Text>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#52c41a",
                      }}
                    >
                      {formatNumber(s.totalStockQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN이동
                    </Text>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#722ed1",
                      }}
                    >
                      {formatNumber(s.totalVnInventoryMoveQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN매출
                    </Text>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#fa8c16",
                      }}
                    >
                      {formatNumber(s.totalVnSalesCompletedQty)}
                    </div>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      VN재고
                    </Text>
                    <div
                      style={{
                        fontSize: 14,
                        fontWeight: 600,
                        fontVariantNumeric: "tabular-nums",
                        color: "#13c2c2",
                      }}
                    >
                      {formatNumber(s.totalVnLocalStockQty)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          marginBottom: 16,
        }}
      >
        <Input
          placeholder="제품명·제품코드 검색"
          prefix={<SearchOutlined />}
          allowClear
          style={{ width: 260 }}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
        />
        <Select
          value={brandFilter}
          onChange={setBrandFilter}
          options={brandOptions}
          style={{ width: 200 }}
          showSearch
          optionFilterProp="label"
        />
        <Select
          value={categoryFilter}
          onChange={setCategoryFilter}
          options={categoryOptions}
          style={{ width: 180 }}
          showSearch
          optionFilterProp="label"
        />
      </div>

      <Table
        columns={columns}
        dataSource={filtered}
        rowKey="id"
        loading={loading}
        size="middle"
        scroll={{ x: 1830 }}
        pagination={{
          pageSize: 50,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100, 200],
          showTotal: (t) => `총 ${t}건`,
        }}
      />
    </div>
  );
}
