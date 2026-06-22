import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined, WarningOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";
import {
  getUploadHistory,
  getUploadHistoryErrors,
  listUploadHistory,
  type UploadHistoryDetail,
  type UploadHistoryErrorsResponse,
  type UploadHistoryItem,
  type UploadStatus,
} from "../../api/uploadHistory";
import { listAccounts, type Account } from "../../api/accounts";
import {
  makeErrorExtractor,
  NOT_FOUND_MESSAGE,
} from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

const extractErrorDetail = makeErrorExtractor({
  statusMessages: {
    404: NOT_FOUND_MESSAGE,
  },
  useAxiosMessage: true,
});

const STATUS_OPTIONS: { value: UploadStatus; label: string; color: string }[] = [
  { value: "completed", label: "완료", color: "green" },
  { value: "partial", label: "일부 실패", color: "orange" },
  { value: "failed", label: "실패", color: "red" },
];

function statusTag(status: UploadStatus) {
  const meta = STATUS_OPTIONS.find((s) => s.value === status);
  return (
    <Tag color={meta?.color ?? "default"} style={{ marginRight: 0 }}>
      {meta?.label ?? status}
    </Tag>
  );
}

export default function UploadHistory() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [items, setItems] = useState<UploadHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [accountId, setAccountId] = useState<string | undefined>();
  const [status, setStatus] = useState<UploadStatus | undefined>();
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [loading, setLoading] = useState(false);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detail, setDetail] = useState<UploadHistoryDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [errorsOpen, setErrorsOpen] = useState(false);
  const [errors, setErrors] = useState<UploadHistoryErrorsResponse | null>(null);
  const [errorsLoading, setErrorsLoading] = useState(false);

  useEffect(() => {
    const run = async () => {
      try {
        const accs = await listAccounts();
        setAccounts(accs);
      } catch {
        // 계좌 못 불러와도 페이지는 동작
      }
    };
    void run();
  }, []);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listUploadHistory({
        page,
        page_size: pageSize,
        account_id: accountId,
        status,
        from: dateRange?.[0]?.format("YYYY-MM-DD"),
        to: dateRange?.[1]?.format("YYYY-MM-DD"),
      });
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "업로드 이력 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, accountId, status, dateRange]);

  useEffect(() => {
    const run = async () => {
      await fetchList();
    };
    void run();
  }, [fetchList]);

  const openDetail = async (id: string) => {
    setDetailOpen(true);
    setDetailLoading(true);
    setDetail(null);
    try {
      const d = await getUploadHistory(id);
      setDetail(d);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "상세 조회 실패"));
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const openErrors = async (id: string) => {
    setErrorsOpen(true);
    setErrorsLoading(true);
    setErrors(null);
    try {
      const e = await getUploadHistoryErrors(id);
      setErrors(e);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "에러 조회 실패"));
      setErrorsOpen(false);
    } finally {
      setErrorsLoading(false);
    }
  };

  const accountOptions = useMemo(
    () =>
      accounts.map((a) => ({
        value: a.id,
        label: `${a.bank_name} · ${a.account_number}`,
      })),
    [accounts],
  );

  const columns: ColumnsType<UploadHistoryItem> = [
    {
      title: "업로드 일시",
      dataIndex: "uploaded_at",
      width: 160,
      render: (v: string) => dayjs(v).format("YYYY-MM-DD HH:mm"),
    },
    {
      title: "파일명",
      dataIndex: "file_name",
      ellipsis: true,
    },
    {
      title: "은행",
      dataIndex: "bank_name",
      width: 110,
      render: (v: string | null) => v || "-",
    },
    {
      title: "기간",
      dataIndex: "period_label",
      width: 130,
      render: (v: string | null) => v || "-",
    },
    {
      title: "신규",
      dataIndex: "imported_count",
      width: 70,
      align: "right",
      render: (v: number) => <Text style={{ color: "#52c41a" }}>{v}</Text>,
    },
    {
      title: "중복",
      dataIndex: "duplicate_count",
      width: 70,
      align: "right",
      render: (v: number) => <Text>{v}</Text>,
    },
    {
      title: "에러",
      dataIndex: "error_count",
      width: 70,
      align: "right",
      render: (v: number) =>
        v > 0 ? <Text style={{ color: "#f5222d" }}>{v}</Text> : <Text>0</Text>,
    },
    {
      title: "상태",
      dataIndex: "status",
      width: 90,
      render: (v: UploadStatus) => statusTag(v),
    },
    {
      title: "",
      width: 160,
      render: (_, record) => (
        <Space size={4}>
          <Button
            type="link"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              void openDetail(record.id);
            }}
          >
            상세
          </Button>
          {record.error_count > 0 && (
            <Button
              type="link"
              size="small"
              danger
              icon={<WarningOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                void openErrors(record.id);
              }}
            >
              에러
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          업로드 이력
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          은행 거래 엑셀 가져오기 이력 · 행 단위 에러 다운로드 지원
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="계좌"
            allowClear
            style={{ width: 240 }}
            options={accountOptions}
            value={accountId}
            onChange={(v) => {
              setAccountId(v);
              setPage(1);
            }}
          />
          <Select
            placeholder="상태"
            allowClear
            style={{ width: 140 }}
            options={STATUS_OPTIONS.map((s) => ({ value: s.value, label: s.label }))}
            value={status}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <RangePicker
            value={dateRange ?? undefined}
            onChange={(v) => {
              setDateRange(v && v[0] && v[1] ? [v[0], v[1]] : null);
              setPage(1);
            }}
          />
          <Button icon={<ReloadOutlined />} onClick={() => void fetchList()}>
            새로고침
          </Button>
        </Space>
      </Card>

      <Table
        columns={columns}
        dataSource={items}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (t) => `총 ${t}건`,
          onChange: (p, ps) => {
            setPage(p);
            setPageSize(ps);
          },
        }}
        onRow={(record) => ({
          onClick: () => {
            void openDetail(record.id);
          },
          style: { cursor: "pointer" },
        })}
      />

      <Modal
        title="업로드 상세"
        open={detailOpen}
        onCancel={() => setDetailOpen(false)}
        footer={[
          <Button key="close" onClick={() => setDetailOpen(false)}>
            닫기
          </Button>,
        ]}
        width={720}
        loading={detailLoading}
      >
        {detail && (
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="업로드 일시" span={2}>
              {dayjs(detail.uploaded_at).format("YYYY-MM-DD HH:mm:ss")}
            </Descriptions.Item>
            <Descriptions.Item label="파일명" span={2}>
              {detail.file_name}
            </Descriptions.Item>
            <Descriptions.Item label="은행">
              {detail.bank_name ?? "-"}
            </Descriptions.Item>
            <Descriptions.Item label="기간">
              {detail.period_label ?? "-"}
            </Descriptions.Item>
            <Descriptions.Item label="계좌" span={2}>
              {detail.account_label ?? detail.account_id ?? "-"}
            </Descriptions.Item>
            <Descriptions.Item label="신규">
              {detail.imported_count}건
            </Descriptions.Item>
            <Descriptions.Item label="중복">
              {detail.duplicate_count}건
            </Descriptions.Item>
            <Descriptions.Item label="에러">
              {detail.error_count}건
            </Descriptions.Item>
            <Descriptions.Item label="상태">
              {statusTag(detail.status)}
            </Descriptions.Item>
            {detail.uploaded_by_name && (
              <Descriptions.Item label="업로더" span={2}>
                {detail.uploaded_by_name}
              </Descriptions.Item>
            )}
            {detail.error_count > 0 && (
              <Descriptions.Item label="에러 상세" span={2}>
                <Button
                  type="link"
                  danger
                  icon={<WarningOutlined />}
                  onClick={() => {
                    setDetailOpen(false);
                    void openErrors(detail.id);
                  }}
                >
                  에러 행 보기
                </Button>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>

      <Modal
        title="가져오기 에러 행"
        open={errorsOpen}
        onCancel={() => setErrorsOpen(false)}
        footer={[
          errors?.download_url ? (
            <Button
              key="download"
              type="primary"
              href={errors.download_url}
              target="_blank"
              rel="noreferrer"
            >
              에러 xlsx 다운로드
            </Button>
          ) : null,
          <Button key="close" onClick={() => setErrorsOpen(false)}>
            닫기
          </Button>,
        ].filter(Boolean) as React.ReactNode[]}
        width={780}
        loading={errorsLoading}
      >
        {errors && (
          <div>
            <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
              총 {errors.total}건의 에러 행
            </Paragraph>
            <div style={{ maxHeight: 420, overflow: "auto" }}>
              {errors.errors.length === 0 ? (
                <Paragraph type="secondary">에러 행이 없습니다.</Paragraph>
              ) : (
                errors.errors.map((e, i) => (
                  <Alert
                    key={i}
                    type="error"
                    style={{ marginBottom: 6 }}
                    message={
                      <Text style={{ fontSize: 12 }}>
                        {typeof e.row_number === "number" ? `행 ${e.row_number}: ` : ""}
                        {e.reason}
                      </Text>
                    }
                  />
                ))
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
