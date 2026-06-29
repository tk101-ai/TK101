import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Empty,
  Input,
  message,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import {
  deleteDocgenDocument,
  listDocgenDocuments,
  type DocgenDocumentBrief,
} from "../../api/docgen";
import {
  listFormJobs,
  listFormTemplates,
  type FormJobSummary,
  type FormTemplateListItem,
} from "../../api/forms";
import { DEPARTMENT_OPTIONS } from "../../config/modules";

const { Text } = Typography;

// 잡 상태 → 표시 라벨/색 + 이어가기 경로.
const JOB_STATUS_META: Record<string, { label: string; color: string }> = {
  analyzing: { label: "분석 중", color: "processing" },
  collecting: { label: "자료 수집", color: "blue" },
  mapping: { label: "매핑 중", color: "gold" },
  reviewing: { label: "검수 중", color: "orange" },
  completed: { label: "완료", color: "green" },
  failed: { label: "실패", color: "red" },
};

function jobResumePath(status: string, id: string): string {
  // collecting/analyzing/failed → 자료 수집 단계, 그 외(mapping/reviewing/completed) → 매핑·완성 단계.
  if (status === "analyzing" || status === "collecting" || status === "failed") {
    return `/forms/jobs/${id}/sources`;
  }
  return `/forms/jobs/${id}/review`;
}

// 양식 잡이 미완료(이어쓰기 대상)인지.
function isInProgress(status: string): boolean {
  return status !== "completed" && status !== "failed";
}

// ── 통합 "내 문서" 항목 공통 형태 ──
type DocKind = "docgen" | "form";

interface MyDocItem {
  key: string;
  kind: DocKind;
  id: string;
  title: string;
  // 상태 라벨/색(docgen 은 항상 완료).
  statusLabel: string;
  statusColor: string;
  // 정렬용 원본 상태 코드(form 잡만 의미 있음).
  rawStatus: string;
  createdAt: string;
}

const KIND_META: Record<DocKind, { label: string; color: string }> = {
  docgen: { label: "문서생성", color: "purple" },
  form: { label: "양식", color: "cyan" },
};

/**
 * 양식 라이브러리(공유) + 내 문서(개인) — FR-07.
 * - 상단: 내 문서(개인) — docgen 생성 문서 + 양식 작성 잡(전 상태)을 한 표로 통합, 생성일시 정렬.
 * - 하단: 양식 라이브러리(공유) — 회사 전체 공유 템플릿.
 */
export default function FormLibraryPage() {
  const navigate = useNavigate();

  // 공유 양식 템플릿(회사 전체).
  const [items, setItems] = useState<FormTemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [dept, setDept] = useState<string | undefined>();

  // 내 문서(개인) — docgen 문서 + 양식 잡.
  const [docgenDocs, setDocgenDocs] = useState<DocgenDocumentBrief[]>([]);
  const [jobs, setJobs] = useState<FormJobSummary[]>([]);
  const [myDocsLoading, setMyDocsLoading] = useState(true);
  const [kindFilter, setKindFilter] = useState<DocKind | undefined>();
  const [statusFilter, setStatusFilter] = useState<string | undefined>();

  const fetch = async () => {
    setLoading(true);
    try {
      const list = await listFormTemplates({ q: q || undefined, dept });
      setItems(list);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "양식 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  };

  const fetchMyDocs = async () => {
    setMyDocsLoading(true);
    // docgen / 양식 잡 각각 독립적으로 실패해도 나머지는 표시.
    const [docsRes, jobsRes] = await Promise.allSettled([
      listDocgenDocuments(),
      listFormJobs(),
    ]);
    setDocgenDocs(docsRes.status === "fulfilled" ? docsRes.value : []);
    setJobs(jobsRes.status === "fulfilled" ? jobsRes.value : []);
    setMyDocsLoading(false);
  };

  useEffect(() => {
    // 마운트 시 공유 양식 + 내 문서(docgen·양식 잡) fetch (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetch();
    void fetchMyDocs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // docgen 문서 + 양식 잡 → 통합 항목(생성일시 내림차순).
  const myDocs = useMemo<MyDocItem[]>(() => {
    const fromDocgen: MyDocItem[] = docgenDocs.map((d) => ({
      key: `docgen:${d.id}`,
      kind: "docgen",
      id: d.id,
      title: d.title || "(제목 없음)",
      statusLabel: "완료",
      statusColor: "green",
      rawStatus: "completed",
      createdAt: d.created_at,
    }));
    const fromJobs: MyDocItem[] = jobs.map((j) => {
      const meta = JOB_STATUS_META[j.status] ?? { label: j.status, color: "default" };
      return {
        key: `form:${j.id}`,
        kind: "form",
        id: j.id,
        title: j.template_name || "양식",
        statusLabel: meta.label,
        statusColor: meta.color,
        rawStatus: j.status,
        createdAt: j.created_at,
      };
    });
    return [...fromDocgen, ...fromJobs].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
  }, [docgenDocs, jobs]);

  // 유형/상태 필터 적용.
  const filteredMyDocs = useMemo(() => {
    return myDocs.filter((it) => {
      if (kindFilter && it.kind !== kindFilter) return false;
      if (statusFilter) {
        if (statusFilter === "in_progress") return it.kind === "form" && isInProgress(it.rawStatus);
        if (statusFilter === "completed") return it.rawStatus === "completed";
        if (statusFilter === "failed") return it.rawStatus === "failed";
      }
      return true;
    });
  }, [myDocs, kindFilter, statusFilter]);

  const handleOpen = (it: MyDocItem) => {
    if (it.kind === "docgen") {
      navigate(`/forms/generate?doc=${encodeURIComponent(it.id)}`);
    } else {
      navigate(jobResumePath(it.rawStatus, it.id));
    }
  };

  const handleDeleteDocgen = async (id: string) => {
    try {
      await deleteDocgenDocument(id);
      setDocgenDocs((prev) => prev.filter((d) => d.id !== id));
      message.success("문서를 삭제했습니다");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 삭제 실패");
    }
  };

  const myDocsColumns: ColumnsType<MyDocItem> = [
    {
      title: "유형",
      dataIndex: "kind",
      width: 110,
      render: (kind: DocKind) => {
        const m = KIND_META[kind];
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: "제목",
      dataIndex: "title",
      render: (v: string, row) => (
        <a onClick={() => handleOpen(row)}>{v}</a>
      ),
    },
    {
      title: "상태",
      dataIndex: "statusLabel",
      width: 110,
      render: (_v, row) => <Tag color={row.statusColor}>{row.statusLabel}</Tag>,
    },
    {
      title: "생성일시",
      dataIndex: "createdAt",
      width: 190,
      defaultSortOrder: "descend",
      sorter: (a, b) =>
        new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      render: (v: string) => (v ? new Date(v).toLocaleString("ko-KR") : "-"),
    },
    {
      title: "동작",
      key: "actions",
      width: 160,
      render: (_v, row) => (
        <Space size={4}>
          <Button size="small" type="link" onClick={() => handleOpen(row)}>
            {row.kind === "form" && isInProgress(row.rawStatus) ? "이어서 작성 →" : "열기"}
          </Button>
          {row.kind === "docgen" && (
            <Popconfirm
              title="이 문서를 삭제할까요?"
              okText="삭제"
              cancelText="취소"
              onConfirm={() => handleDeleteDocgen(row.id)}
            >
              <Button size="small" type="link" danger>
                삭제
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const columns: ColumnsType<FormTemplateListItem> = [
    {
      title: "양식명",
      dataIndex: "name",
      render: (v, row) => (
        <Space>
          <a onClick={() => navigate(`/forms/templates/${row.id}/review`)}>{v}</a>
          <Tag>v{row.version}</Tag>
          <Tag color="blue">{(row.file_format ?? "docx").toUpperCase()}</Tag>
        </Space>
      ),
    },
    {
      title: "부서 태그",
      dataIndex: "department_tags",
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {tags.length === 0 ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              -
            </Text>
          ) : (
            tags.map((t) => <Tag key={t}>{t}</Tag>)
          )}
        </Space>
      ),
    },
    { title: "사용 횟수", dataIndex: "usage_count", width: 100 },
    {
      title: "수정일",
      dataIndex: "updated_at",
      width: 180,
      render: (v: string | undefined, row) => {
        const dt = v ?? row.created_at;
        return dt ? new Date(dt).toLocaleString("ko-KR") : "-";
      },
    },
  ];

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            내 문서 · 양식 라이브러리
          </h2>
          <Text type="secondary">내가 만든 문서(개인)와 회사 공유 양식을 한 곳에서 관리합니다.</Text>
        </div>
        <Space>
          <Button type="primary" onClick={() => navigate("/forms/generate?wizard=1")}>
            문서 만들기
          </Button>
          <Button onClick={() => navigate("/forms/new")}>새 양식 업로드</Button>
        </Space>
      </div>

      {/* ── 내 문서(개인) ── */}
      <div style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>
          내 문서(개인){" "}
          <Text type="secondary" style={{ fontSize: 12, fontWeight: 400 }}>
            ({filteredMyDocs.length})
          </Text>
        </h3>
        <Text type="secondary" style={{ fontSize: 12 }}>
          본인이 생성한 문서(문서생성)와 양식 작성 내역(전 상태)입니다. 생성일시 기준 최신순으로 정렬됩니다.
        </Text>
      </div>

      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="유형 필터"
          value={kindFilter}
          onChange={(v) => setKindFilter(v)}
          style={{ width: 160 }}
          options={[
            { label: "문서생성", value: "docgen" },
            { label: "양식", value: "form" },
          ]}
        />
        <Select
          allowClear
          placeholder="상태 필터"
          value={statusFilter}
          onChange={(v) => setStatusFilter(v)}
          style={{ width: 160 }}
          options={[
            { label: "작성 중", value: "in_progress" },
            { label: "완료", value: "completed" },
            { label: "실패", value: "failed" },
          ]}
        />
        <Button onClick={fetchMyDocs}>새로고침</Button>
      </Space>

      {filteredMyDocs.length === 0 && !myDocsLoading ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="아직 내 문서가 없습니다 — '새 문서 작성' 또는 '양식 채우기'로 시작하세요"
          style={{ marginTop: 24, marginBottom: 32 }}
        />
      ) : (
        <Table
          loading={myDocsLoading}
          rowKey="key"
          dataSource={filteredMyDocs}
          columns={myDocsColumns}
          size="small"
          pagination={{ pageSize: 10 }}
          style={{ marginBottom: 32 }}
        />
      )}

      {/* ── 양식 라이브러리(공유) ── */}
      <div style={{ marginBottom: 8 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>양식 라이브러리(공유)</h3>
        <Text type="secondary" style={{ fontSize: 12 }}>
          회사 전체가 공유하는 양식 템플릿입니다. 위 '내 문서'(개인 작성 내역)와 달리 부서/전사 공용입니다.
        </Text>
      </div>

      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search
          placeholder="양식명 검색"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onSearch={fetch}
          style={{ width: 280 }}
        />
        <Select
          allowClear
          placeholder="부서 필터"
          options={DEPARTMENT_OPTIONS}
          value={dept}
          onChange={(v) => setDept(v)}
          style={{ width: 200 }}
          onBlur={fetch}
        />
        <Button onClick={fetch}>새로고침</Button>
      </Space>

      {items.length === 0 && !loading ? (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="등록된 양식이 없습니다 — 우상단 '새 양식 업로드'로 시작하세요"
          style={{ marginTop: 24 }}
        />
      ) : (
        <Table
          loading={loading}
          rowKey="id"
          dataSource={items}
          columns={columns}
          size="small"
          pagination={{ pageSize: 20 }}
        />
      )}
    </div>
  );
}
