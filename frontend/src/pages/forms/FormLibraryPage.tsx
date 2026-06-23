import { useEffect, useState } from "react";
import { Button, Card, Empty, Input, message, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
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

/**
 * 양식 라이브러리 — FR-07.
 * Phase 1 골격: 검색·필터·재사용 진입점만 제공.
 */
export default function FormLibraryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<FormTemplateListItem[]>([]);
  const [jobs, setJobs] = useState<FormJobSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [dept, setDept] = useState<string | undefined>();

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

  const fetchJobs = async () => {
    try {
      setJobs(await listFormJobs());
    } catch {
      // 작성 중 문서 목록 실패는 비치명적 — 라이브러리는 정상 표시.
    }
  };

  useEffect(() => {
    // 마운트 시 폼 라이브러리 + 작성 중 문서 fetch (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetch();
    void fetchJobs();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 작성 중(미완료) 문서 — resume 대상. 완료/실패는 제외(필요 시 재진입은 라이브러리 외).
  const inProgressJobs = jobs.filter(
    (j) => j.status !== "completed" && j.status !== "failed",
  );

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
            양식 라이브러리
          </h2>
          <Text type="secondary">회사 전체 공유 + 부서 태그</Text>
        </div>
        <Button type="primary" onClick={() => navigate("/forms/new")}>
          새 양식 업로드
        </Button>
      </div>

      {inProgressJobs.length > 0 && (
        <Card
          size="small"
          title={`작성 중 문서 (${inProgressJobs.length})`}
          style={{ marginBottom: 16 }}
          bodyStyle={{ padding: "4px 0" }}
        >
          {inProgressJobs.map((j) => {
            const meta = JOB_STATUS_META[j.status] ?? { label: j.status, color: "default" };
            return (
              <div
                key={j.id}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "8px 16px",
                  borderBottom: "1px solid #f5f5f5",
                }}
              >
                <Space>
                  <Tag color={meta.color}>{meta.label}</Tag>
                  <Text>{j.template_name || "(양식 미상)"}</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {new Date(j.created_at).toLocaleString("ko-KR")}
                  </Text>
                </Space>
                <Button
                  size="small"
                  type="link"
                  onClick={() => navigate(jobResumePath(j.status, j.id))}
                >
                  이어서 작성 →
                </Button>
              </div>
            );
          })}
        </Card>
      )}

      <Space style={{ marginBottom: 12 }}>
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
          style={{ marginTop: 48 }}
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
