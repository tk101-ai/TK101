import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  DatePicker,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  ReloadOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { Dayjs } from "dayjs";
import { Link } from "react-router-dom";
import {
  COMPANY_FILTER_OPTIONS,
  type DistributionCompany,
  listWeeklySummary,
  type WeeklySummaryOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

type CompanyChoice = DistributionCompany | "all";

/**
 * 주차별 종합 데이터 조회 페이지 (T9 Phase B-1 / E-3 기간필터).
 *
 * 백엔드: `GET /api/distribution/data/weekly-summary`
 * - 페이지 사이즈 20
 * - 금액 컬럼은 천단위 콤마 + 우측 정렬 + monospace
 * - 상단 RangePicker 로 period 기간 필터링
 */
export default function WeeklyDataPage() {
  const [data, setData] = useState<WeeklySummaryOut[]>([]);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [company, setCompany] = useState<CompanyChoice>("all");

  const filter = useMemo(() => {
    const [from, to] = range ?? [null, null];
    return {
      limit: 200,
      from: from ? from.format("YYYY-MM-DD") : undefined,
      to: to ? to.format("YYYY-MM-DD") : undefined,
      company_label: company === "all" ? undefined : company,
    };
  }, [range, company]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listWeeklySummary(filter);
      // backend 가 company_label 필터를 무시할 가능성에 대비한 클라이언트 측 폴백.
      const finalItems =
        company === "all"
          ? items
          : items.filter((r) => r.company_label === company);
      setData(finalItems);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "주차별 데이터 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter, company]);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  const handleReset = () => {
    setRange(null);
    setCompany("all");
  };

  const columns: ColumnsType<WeeklySummaryOut> = [
    {
      title: "회사",
      dataIndex: "company_label",
      width: 120,
      fixed: "left",
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
    },
    {
      title: "기간",
      dataIndex: "period_label",
      width: 140,
      fixed: "left",
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "시작일",
      dataIndex: "period_start",
      width: 110,
      render: (v: string) => (
        <Text style={{ fontSize: 12 }}>{formatDate(v)}</Text>
      ),
    },
    {
      title: "종료일",
      dataIndex: "period_end",
      width: 110,
      render: (v: string) => (
        <Text style={{ fontSize: 12 }}>{formatDate(v)}</Text>
      ),
    },
    amountColumn("KR매입", "kr_purchase"),
    amountColumn("VN재고이동", "vn_inventory_move"),
    amountColumn("VN매출완료", "vn_sales_completed"),
    amountColumn("KR입금요청", "kr_purchase_deposit_req"),
    amountColumn("VN재고입금요청", "vn_inventory_deposit_req"),
    amountColumn("VN매출입금요청", "vn_sales_deposit_req"),
    amountColumn("계좌입금", "account_deposit"),
    amountColumn("현금", "cash_deposit"),
    {
      title: "업로드 파일",
      dataIndex: "source_file",
      width: 220,
      render: (v: string | null) =>
        v ? (
          <Text type="secondary" style={{ fontSize: 12 }}>
            {v}
          </Text>
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
            주차별 종합 데이터
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            래더엑스 종합관리시트의 회사별 주차별 매입/매출/입금 현황입니다.
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

      {/* 회사·기간 필터 영역 */}
      <div
        style={{
          marginBottom: 16,
          padding: "12px 16px",
          background: "#fafafa",
          borderRadius: 6,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <Text strong style={{ marginRight: 4 }}>
          회사
        </Text>
        <Select<CompanyChoice>
          value={company}
          onChange={(v) => setCompany(v)}
          options={COMPANY_FILTER_OPTIONS}
          style={{ width: 200 }}
        />
        <Text strong style={{ marginLeft: 8, marginRight: 4 }}>
          기간
        </Text>
        <RangePicker
          value={range}
          onChange={(v) => setRange(v ? [v[0] ?? null, v[1] ?? null] : null)}
          format="YYYY-MM-DD"
          allowClear
          placeholder={["시작일", "종료일"]}
        />
        <Button
          icon={<UndoOutlined />}
          onClick={handleReset}
          disabled={
            company === "all" && (!range || (!range[0] && !range[1]))
          }
        >
          초기화
        </Button>
      </div>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        scroll={{ x: 1800 }}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (t) => `총 ${t}건`,
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

function formatDate(iso: string): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD");
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

/**
 * 금액 컬럼 팩토리. 천단위 콤마 + 우측 정렬 + monospace.
 * `key`는 WeeklySummaryOut 의 string|null 필드명만 허용.
 */
type AmountKey = {
  [K in keyof WeeklySummaryOut]: WeeklySummaryOut[K] extends string | null
    ? K
    : never;
}[keyof WeeklySummaryOut];

function amountColumn(
  title: string,
  key: AmountKey,
): ColumnsType<WeeklySummaryOut>[number] {
  return {
    title,
    dataIndex: key,
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
  };
}
