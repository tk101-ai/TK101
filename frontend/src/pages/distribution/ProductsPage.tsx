import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Input,
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
import { listProducts, type ProductOut } from "../../api/distribution";
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
  // 정확 매칭 우선, 그 다음 부분 매칭 (대소문자 무시).
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

// ---------------------------------------------------------------------------
// 페이지
// ---------------------------------------------------------------------------

/**
 * 명품재고대장 조회 페이지 (T9 Phase B-1).
 *
 * 백엔드: `GET /api/distribution/data/products`
 * - 브랜드 / 카테고리 / 검색(제품명·코드) 필터
 * - 상단 브랜드별 그룹 통계 (제품 수, 총 매입수량)
 * - 페이지 사이즈 50
 */
export default function ProductsPage() {
  const [data, setData] = useState<ProductOut[]>([]);
  const [loading, setLoading] = useState(false);

  const [brandFilter, setBrandFilter] = useState<string>("all");
  const [categoryFilter, setCategoryFilter] = useState<string>("all");
  const [searchInput, setSearchInput] = useState("");

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listProducts(1000);
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

  // 브랜드 목록 (필터 옵션용)
  const brandOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of data) set.add(p.brand);
    return [
      { value: "all", label: "전체 브랜드" },
      ...Array.from(set)
        .sort()
        .map((b) => ({ value: b, label: b })),
    ];
  }, [data]);

  // 카테고리 목록 (필터 옵션용)
  const categoryOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of data) {
      if (p.category) set.add(p.category);
    }
    return [
      { value: "all", label: "전체 카테고리" },
      ...Array.from(set)
        .sort()
        .map((c) => ({ value: c, label: c })),
    ];
  }, [data]);

  // 브랜드별 그룹 통계 (필터 적용 전 전체 데이터 기준)
  const brandStats = useMemo(() => {
    const map = new Map<string, { count: number; totalQty: number }>();
    for (const p of data) {
      const prev = map.get(p.brand) ?? { count: 0, totalQty: 0 };
      map.set(p.brand, {
        count: prev.count + 1,
        totalQty: prev.totalQty + (p.purchase_qty ?? 0),
      });
    }
    return Array.from(map.entries())
      .map(([brand, stats]) => ({ brand, ...stats }))
      .sort((a, b) => b.count - a.count);
  }, [data]);

  // 필터 적용
  const filtered = useMemo(() => {
    const q = searchInput.trim().toLowerCase();
    return data.filter((p) => {
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
  }, [data, brandFilter, categoryFilter, searchInput]);

  const columns: ColumnsType<ProductOut> = [
    {
      title: "브랜드",
      dataIndex: "brand",
      width: 140,
      fixed: "left",
      render: (v: string) => <Tag color={getBrandColor(v)}>{v}</Tag>,
    },
    {
      title: "제품명(영문)",
      dataIndex: "product_name_en",
      width: 240,
      render: (v: string | null) =>
        v ? (
          <Text>{v}</Text>
        ) : (
          <Text type="secondary">—</Text>
        ),
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
        v ? <Tag color={getCategoryColor(v)}>{v}</Tag> : <Text type="secondary">—</Text>,
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
            업로드된 명품재고 전체 목록입니다. 매주 업로드 시 전체 갱신됩니다.
          </Paragraph>
        </div>
        <Space>
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

      {brandStats.length > 0 && (
        <Card size="small" style={{ marginBottom: 16 }} title="브랜드별 요약">
          <div
            style={{
              display: "grid",
              gap: 12,
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
            }}
          >
            {brandStats.map((s) => (
              <div
                key={s.brand}
                style={{
                  padding: 12,
                  background: "#fafafa",
                  borderRadius: 6,
                }}
              >
                <Tag color={getBrandColor(s.brand)} style={{ marginBottom: 8 }}>
                  {s.brand}
                </Tag>
                <Space size="large">
                  <Statistic
                    title="제품 수"
                    value={s.count}
                    valueStyle={{ fontSize: 18 }}
                  />
                  <Statistic
                    title="총 매입수량"
                    value={s.totalQty}
                    valueStyle={{ fontSize: 18 }}
                  />
                </Space>
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
        scroll={{ x: 1400 }}
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
