import { useEffect, useState } from "react";
import { Button, Empty, Input, message, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import { listFormTemplates, type FormTemplateListItem } from "../../api/forms";
import { DEPARTMENT_OPTIONS } from "../../config/modules";

const { Text } = Typography;

/**
 * 양식 라이브러리 — FR-07.
 * Phase 1 골격: 검색·필터·재사용 진입점만 제공.
 */
export default function FormLibraryPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<FormTemplateListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [dept, setDept] = useState<string | undefined>();

  const fetch = async () => {
    setLoading(true);
    try {
      const list = await listFormTemplates({ q: q || undefined, dept });
      setItems(list);
    } catch {
      message.error("양식 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
            양식 라이브러리{" "}
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              v0.1 (Phase 1 골격)
            </Text>
          </h2>
          <Text type="secondary">회사 전체 공유 + 부서 태그</Text>
        </div>
        <Button type="primary" onClick={() => navigate("/forms/new")}>
          새 양식 업로드
        </Button>
      </div>

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
