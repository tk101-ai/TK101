import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CommentOutlined,
  DownloadOutlined,
  LineChartOutlined,
  LinkOutlined,
  PlusOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  CONTENT_TYPE_OPTIONS,
  PRODUCER_OPTIONS,
  collectComments,
  collectMetrics,
  createManualContent,
  exportPosts,
  getContentTypeLabel,
  listAccounts,
  listPosts,
  type CreateContentRequest,
  type SnsAccount,
  type SnsPost,
} from "../../api/sns";
import AccountSelector, {
  buildAccountLabel,
  isConnectedAccount,
} from "../../components/sns/AccountSelector";
import { extractErrorDetail } from "../../utils/errorUtils";
import PostMetricsDrawer from "./PostMetricsDrawer";

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

// 서울시 SNS — Meta 우선. 페이스북/인스타그램.
const NUMBER_FORMATTER = new Intl.NumberFormat("ko-KR");
const POSTS_PER_ACCOUNT = 500;

function fmt(value: number | null | undefined): string {
  if (value == null) return "-";
  return NUMBER_FORMATTER.format(value);
}

interface ContentFormValues {
  posted_at: Dayjs;
  title?: string;
  content_type?: string;
  producer?: string;
  url?: string;
}

/**
 * SNS 콘텐츠 DB 페이지 — 마케팅 전 직원 공용 SNS 단일 페이지 (T1, Meta 우선).
 *
 * - 다중 계정 선택(AccountSelector) + 기간(RangePicker) 으로 조회 대상을 자유롭게 구성.
 *   계정을 정확히 1개 선택하면 그 계정이 수집·수동등록의 대상이 된다(미선택 시 전체 연결 계정 조회).
 * - 콘텐츠 리스트 테이블: 배포일/계정/제목/형태/조회수/좋아요/댓글/공유/합계/URL.
 * - 수동 콘텐츠 추가 폼 (배포일/제목/형태/제작주체/URL) → is_manual.
 * - 게시물별 메트릭 시계열 보기 (Drawer).
 *
 * 무료 수집(게시물·메트릭/댓글)은 마케팅 SNS 권한 전 직원에게 개방된다.
 * 자동 수집은 메타 토큰이 등록된 계정에서만 동작하며, 수동 콘텐츠 등록은 토큰 없이도 동작한다.
 */
export default function SeoulSns() {
  const [accounts, setAccounts] = useState<SnsAccount[]>([]);
  // 조회(뷰) 필터 — 여러 계정/기간을 동시에 볼 수 있다.
  // 정확히 1개 선택 시 그 계정이 수집·수동등록의 대상(actionAccount)이 된다.
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [dateFrom, setDateFrom] = useState<string | undefined>();
  const [dateTo, setDateTo] = useState<string | undefined>();
  const [posts, setPosts] = useState<SnsPost[]>([]);
  const [loading, setLoading] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [metricsPost, setMetricsPost] = useState<SnsPost | null>(null);
  const [collecting, setCollecting] = useState(false);
  const [collectingComments, setCollectingComments] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [form] = Form.useForm<ContentFormValues>();

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await listAccounts();
      setAccounts(res.data);
    } catch (err) {
      message.error(extractErrorDetail(err, "계정 목록 조회 실패"));
    }
  }, []);

  useEffect(() => {
    void fetchAccounts();
  }, [fetchAccounts]);

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.id, a])), [accounts]);

  // 수집/수동등록의 대상 계정: 정확히 1개를 선택했을 때만 결정된다.
  const actionAccount = useMemo(
    () => (selectedAccountIds.length === 1 ? accountMap.get(selectedAccountIds[0]) ?? null : null),
    [selectedAccountIds, accountMap],
  );

  // 조회 대상 계정: 선택이 있으면 그 계정들, 없으면 전체 연결 계정(기본은 모두 보기).
  const viewAccountIds = useMemo(() => {
    if (selectedAccountIds.length > 0) return selectedAccountIds;
    return accounts.filter(isConnectedAccount).map((a) => a.id);
  }, [selectedAccountIds, accounts]);

  const fetchPosts = useCallback(async () => {
    if (viewAccountIds.length === 0) {
      setPosts([]);
      return;
    }
    setLoading(true);
    try {
      // listPosts 는 단일 account_id 만 지원 → 계정별로 조회 후 병합. 기간은 공통 적용.
      const responses = await Promise.all(
        viewAccountIds.map((id) =>
          listPosts({
            account_id: id,
            date_from: dateFrom,
            date_to: dateTo,
            limit: POSTS_PER_ACCOUNT,
          }),
        ),
      );
      const merged = responses
        .flatMap((res) => res.data)
        .sort((a, b) => b.posted_at.localeCompare(a.posted_at));
      setPosts(merged);
    } catch (err) {
      message.error(extractErrorDetail(err, "콘텐츠 목록 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [viewAccountIds, dateFrom, dateTo]);

  useEffect(() => {
    void fetchPosts();
  }, [fetchPosts]);

  const handleAdd = async (values: ContentFormValues) => {
    if (!actionAccount) {
      message.warning("콘텐츠를 추가할 계정을 1개 선택하세요");
      return;
    }
    const payload: CreateContentRequest = {
      posted_at: values.posted_at.format("YYYY-MM-DD"),
      title: values.title ?? null,
      content_type: values.content_type ?? null,
      producer: values.producer ?? null,
      url: values.url ?? null,
    };
    try {
      await createManualContent(actionAccount.id, payload);
      message.success("콘텐츠 등록 완료");
      setAddOpen(false);
      form.resetFields();
      void fetchPosts();
    } catch (err) {
      message.error(extractErrorDetail(err, "콘텐츠 등록 실패"));
    }
  };

  const handleCollectMetrics = async () => {
    if (!actionAccount) {
      message.warning("수집/추가할 계정을 정확히 1개 선택하세요");
      return;
    }
    setCollecting(true);
    try {
      const res = await collectMetrics(actionAccount.id, "daily");
      const {
        posts_processed,
        snapshots_added,
        snapshots_updated,
        posts_added,
        posts_updated,
        failures,
      } = res.data;
      message.success(
        `수집 완료 — 신규 게시물 ${posts_added} · 게시물 갱신 ${posts_updated} · ` +
          `메트릭 처리 ${posts_processed}(신규 ${snapshots_added}/갱신 ${snapshots_updated})`,
      );
      if (failures.length > 0) {
        message.warning(`일부 실패 ${failures.length}건 (콘솔/응답 확인)`);
      }
      void fetchPosts();
    } catch (err) {
      message.error(
        extractErrorDetail(err, "메트릭 수집 실패", {
          statusMessages: { 501: "이 플랫폼은 메트릭 수집 미지원" },
        }),
      );
    } finally {
      setCollecting(false);
    }
  };

  const handleCollectComments = async () => {
    if (!actionAccount) {
      message.warning("수집/추가할 계정을 정확히 1개 선택하세요");
      return;
    }
    setCollectingComments(true);
    try {
      const res = await collectComments(actionAccount.id);
      const { posts_processed, comments_added, comments_updated, failures } = res.data;
      message.success(
        `댓글 수집 완료 — 게시물 ${posts_processed} · 신규 ${comments_added} · 갱신 ${comments_updated}`,
      );
      if (failures.length > 0) {
        message.warning(`일부 실패 ${failures.length}건 (콘솔/응답 확인)`);
      }
    } catch (err) {
      message.error(
        extractErrorDetail(err, "댓글 수집 실패", {
          statusMessages: { 501: "이 플랫폼은 댓글 수집 미지원" },
        }),
      );
    } finally {
      setCollectingComments(false);
    }
  };

  // 현재 조회(뷰) 필터 그대로 게시물 .xlsx 내보내기.
  // 단일 계정 조회면 account_id 를 보내고, 다중/미선택이면 생략 → 백엔드가 기간 내
  // 전체 계정 게시물을 (계정 식별 컬럼 포함) 내보낸다.
  const handleExport = async () => {
    setExporting(true);
    try {
      await exportPosts({
        account_id: viewAccountIds.length === 1 ? viewAccountIds[0] : undefined,
        date_from: dateFrom,
        date_to: dateTo,
      });
    } catch (err) {
      message.error(extractErrorDetail(err, "엑셀 내보내기 실패"));
    } finally {
      setExporting(false);
    }
  };

  // 현재 조회 대상(계정·기간) 사람이 읽는 요약. "조회 중: 유튜브·Seoul, 인스타·seoul · 2026-05-01~05-31"
  const viewingSummary = useMemo(() => {
    const labels = viewAccountIds
      .map((id) => accountMap.get(id))
      .filter((a): a is SnsAccount => !!a)
      .map((a) => buildAccountLabel(a));
    const accountsPart = labels.length > 0 ? labels.join(", ") : "선택된 계정 없음";
    const periodPart =
      dateFrom || dateTo ? ` · ${dateFrom ?? "처음"}~${dateTo ?? "현재"}` : " · 전체 기간";
    return `${accountsPart}${periodPart}`;
  }, [viewAccountIds, accountMap, dateFrom, dateTo]);

  const columns: ColumnsType<SnsPost> = [
    {
      title: "배포일",
      dataIndex: "posted_at",
      width: 108,
      fixed: "left" as const,
      sorter: (a, b) => a.posted_at.localeCompare(b.posted_at),
      defaultSortOrder: "descend" as const,
    },
    {
      title: "계정",
      dataIndex: "account_id",
      width: 168,
      render: (id: string) => {
        const acct = accountMap.get(id);
        return acct ? buildAccountLabel(acct) : id.slice(0, 8);
      },
    },
    {
      title: "제목",
      dataIndex: "title",
      ellipsis: true,
      render: (v: string | null, record) => (
        <Space size={6}>
          {record.is_manual ? (
            <Tag color="gold" style={{ marginInlineEnd: 0 }}>
              수동
            </Tag>
          ) : (
            <Tag color="geekblue" style={{ marginInlineEnd: 0 }}>
              자동
            </Tag>
          )}
          <span>{v || "(제목 없음)"}</span>
        </Space>
      ),
    },
    {
      title: "형태",
      dataIndex: "content_type",
      width: 84,
      render: (v: string | null) => (v ? <Tag color="purple">{getContentTypeLabel(v)}</Tag> : "-"),
    },
    {
      title: "제작주체",
      dataIndex: "producer",
      width: 110,
      render: (v: string | null) => v || "-",
    },
    {
      title: "조회수",
      dataIndex: "view_count",
      width: 96,
      align: "right" as const,
      render: fmt,
    },
    {
      title: "좋아요",
      dataIndex: "like_count",
      width: 84,
      align: "right" as const,
      render: fmt,
    },
    {
      title: "댓글",
      dataIndex: "comment_count",
      width: 78,
      align: "right" as const,
      render: fmt,
    },
    {
      title: "공유",
      dataIndex: "share_count",
      width: 78,
      align: "right" as const,
      render: fmt,
    },
    {
      title: "합계",
      dataIndex: "total_engagement",
      width: 90,
      align: "right" as const,
      render: (v: number | null) =>
        v != null ? <Text strong>{fmt(v)}</Text> : "-",
    },
    {
      title: "URL",
      dataIndex: "url",
      width: 60,
      render: (v: string | null) =>
        v ? (
          <Button type="link" size="small" icon={<LinkOutlined />} href={v} target="_blank" />
        ) : (
          "-"
        ),
    },
    {
      title: "추이",
      width: 72,
      fixed: "right" as const,
      render: (_, record) => (
        <Tooltip title="메트릭 시계열 보기">
          <Button
            type="text"
            size="small"
            icon={<LineChartOutlined />}
            onClick={() => setMetricsPost(record)}
          />
        </Tooltip>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1320 }}>
      <header style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          SNS 콘텐츠
        </Title>
        <Text type="secondary">
          페이스북 · 인스타그램 등 계정을 한 곳에서 조회합니다. 자동(메타 API) / 수동(직접 입력) 두 모드 지원.
        </Text>
      </header>

      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 20 }}
        message="자동 모드는 메타 API 토큰이 등록되어야 동작합니다"
        description="토큰 미설정 시 자동 수집은 비활성화되며, 수동 콘텐츠 등록은 정상 동작합니다. '게시물·메트릭 수집'을 누르면 신규 게시물을 가져오고 조회수/좋아요/댓글/공유를 채웁니다. (페이스북 일반 게시물은 메타가 조회수를 제공하지 않아 영상/릴스만 표시됩니다.)"
      />

      {/* 조회(뷰) 필터 — 다중 계정 + 기간. 1개만 선택하면 그 계정이 수집/추가 대상이 된다. */}
      <Space wrap size={12} style={{ marginBottom: 12 }}>
        <AccountSelector
          mode="multi"
          accounts={accounts}
          value={selectedAccountIds}
          onChange={setSelectedAccountIds}
          placeholder="조회할 계정 선택 (여러 개 가능 · 수집/추가는 1개만)"
          style={{ minWidth: 360 }}
        />
        <RangePicker
          onChange={(_, dates) => {
            setDateFrom(dates?.[0] || undefined);
            setDateTo(dates?.[1] || undefined);
          }}
        />
        <Button
          icon={<DownloadOutlined />}
          loading={exporting}
          disabled={viewAccountIds.length === 0}
          onClick={handleExport}
        >
          엑셀 내보내기
        </Button>
      </Space>

      {/* 수집/수동등록 액션 — 계정을 정확히 1개 선택했을 때만 활성화. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          gap: 8,
          margin: "12px 0",
        }}
      >
        {actionAccount && (
          <Text type="secondary" style={{ marginInlineEnd: 4 }}>
            대상: <Text strong>{buildAccountLabel(actionAccount)}</Text>
          </Text>
        )}
        <Tooltip
          title={
            actionAccount
              ? undefined
              : "조회 계정을 정확히 1개 선택하면 그 계정에 수집/추가합니다"
          }
        >
          <Space size={8}>
            <Button
              icon={<ThunderboltOutlined />}
              loading={collecting}
              disabled={!actionAccount}
              onClick={handleCollectMetrics}
            >
              게시물·메트릭 수집
            </Button>
            <Button
              icon={<CommentOutlined />}
              loading={collectingComments}
              disabled={!actionAccount}
              onClick={handleCollectComments}
            >
              댓글 수집 (자동)
            </Button>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              disabled={!actionAccount}
              onClick={() => setAddOpen(true)}
            >
              콘텐츠 추가 (수동)
            </Button>
          </Space>
        </Tooltip>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message={
          <span>
            조회 중: <Text strong>{viewingSummary}</Text>
          </span>
        }
      />

      <Spin spinning={loading}>
        {viewAccountIds.length > 0 ? (
          <Table
            columns={columns}
            dataSource={posts}
            rowKey="id"
            size="middle"
            pagination={{ pageSize: 50, showTotal: (t) => `총 ${t}건` }}
            scroll={{ x: 1280 }}
            locale={{ emptyText: <Empty description="콘텐츠가 없습니다" /> }}
          />
        ) : (
          <Empty description="표시할 콘텐츠가 없습니다" style={{ padding: "48px 0" }} />
        )}
      </Spin>

      <Modal
        title="콘텐츠 추가 (수동)"
        open={addOpen}
        onCancel={() => setAddOpen(false)}
        onOk={() => form.submit()}
        okText="등록"
        cancelText="취소"
        destroyOnClose
        width={560}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Form.Item
            name="posted_at"
            label="배포일"
            rules={[{ required: true, message: "배포일을 선택하세요" }]}
            initialValue={dayjs()}
          >
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="title" label="콘텐츠 제목">
            <Input.TextArea rows={2} placeholder="콘텐츠 제목" />
          </Form.Item>
          <Space size={16} style={{ display: "flex", flexWrap: "wrap" }}>
            <Form.Item name="content_type" label="형태" style={{ minWidth: 200 }}>
              <Select options={CONTENT_TYPE_OPTIONS} placeholder="형태 선택" allowClear />
            </Form.Item>
            <Form.Item name="producer" label="제작주체" style={{ minWidth: 200 }}>
              <Select options={PRODUCER_OPTIONS} placeholder="제작주체 선택" allowClear />
            </Form.Item>
          </Space>
          <Form.Item name="url" label="URL 링크">
            <Input placeholder="https://..." />
          </Form.Item>
        </Form>
      </Modal>

      <PostMetricsDrawer
        post={metricsPost}
        onClose={() => setMetricsPost(null)}
      />
    </div>
  );
}
