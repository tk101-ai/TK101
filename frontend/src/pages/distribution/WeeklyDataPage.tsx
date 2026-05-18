import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { Link } from "react-router-dom";
import {
  listWeeklySummary,
  type WeeklySummaryOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;

/**
 * 주차별 종합 데이터 조회 페이지 (T9 Phase B-1).
 *
 * 백엔드: `GET /api/distribution/data/weekly-summary`
 * - 페이지 사이즈 20
 * - 금액 컬럼은 천단위 콤마 + 우측 정렬 + monospace
 */
export default function WeeklyDataPage() {
  const [data, setData] = useState<WeeklySummaryOut[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listWeeklySummary(200);
      setData(items);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "주차별 데이터 조회 실패"));
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
