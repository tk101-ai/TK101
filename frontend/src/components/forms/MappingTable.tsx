import { useEffect, useState } from "react";
import { Badge, Button, Input, Space, Table, Tag, Typography } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type {
  FormDataSource,
  FormMapping,
  FormTemplate,
  FormVariable,
} from "../../api/forms";
import SourceMetaPopover from "./SourceMetaPopover";

const { Text } = Typography;

interface MappingTableProps {
  template: FormTemplate;
  mappings: FormMapping[];
  sources: FormDataSource[];
  onValueChange: (variableKey: string, value: string) => void;
  onRegenerate: (variableKey: string) => void;
  loading?: boolean;
  regeneratingKey?: string | null;
}

interface Row {
  variable: FormVariable;
  mapping: FormMapping | null;
}

/**
 * 값 입력 셀 — 로컬 상태로 타이핑을 흡수하고, 포커스 해제(blur) 또는 Enter 시에만
 * 부모로 커밋한다. 과거엔 키 입력마다 onChange → PATCH + 전체 새로고침이 발생했다.
 * 외부에서 값이 갱신되면(재생성 등) prop 변화를 로컬에 동기화한다.
 */
function ValueCell({
  value,
  placeholder,
  onCommit,
}: {
  value: string;
  placeholder: string;
  onCommit: (next: string) => void;
}) {
  const [draft, setDraft] = useState(value);

  useEffect(() => {
    setDraft(value);
  }, [value]);

  const commit = () => {
    if (draft !== value) onCommit(draft);
  };

  return (
    <Input
      size="small"
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onPressEnter={commit}
    />
  );
}

function statusBadge(row: Row) {
  const m = row.mapping;
  if (!m || m.value === null || m.value === "") {
    return <Tag color="red">누락</Tag>;
  }
  if (m.llm_confidence !== null && m.llm_confidence < 0.8 && m.llm_confidence >= 0.5) {
    return <Tag color="orange">확인 필요</Tag>;
  }
  if (m.manual_override) {
    return <Tag color="blue">수동</Tag>;
  }
  return <Tag color="green">자동 채움</Tag>;
}

/**
 * 검수 UI 우측 — 변수 매핑 테이블.
 * 누락 변수 빨간 배지, confidence 0.5~0.8 노란 배지, 출처 1클릭 펼쳐보기.
 */
export default function MappingTable({
  template,
  mappings,
  sources,
  onValueChange,
  onRegenerate,
  loading,
  regeneratingKey,
}: MappingTableProps) {
  const sourceById = new Map(sources.map((s) => [s.id, s]));

  const rows: Row[] = template.variables.map((v) => {
    const m = mappings.find((mp) => mp.variable_key === v.key) ?? null;
    return { variable: v, mapping: m };
  });

  const missingCount = rows.filter(
    (r) => !r.mapping || r.mapping.value === null || r.mapping.value === "",
  ).length;

  const columns: ColumnsType<Row> = [
    {
      title: "변수",
      dataIndex: ["variable", "label"],
      width: 160,
      render: (_, row) => (
        <div>
          <div style={{ fontWeight: 500 }}>
            {row.variable.label}
            {row.variable.required && (
              <Text type="danger" style={{ marginLeft: 4 }}>
                *
              </Text>
            )}
          </div>
          <Text type="secondary" style={{ fontSize: 11 }}>
            {row.variable.key} · {row.variable.type}
          </Text>
        </div>
      ),
    },
    {
      title: "값",
      dataIndex: ["mapping", "value"],
      render: (_, row) => (
        <ValueCell
          value={row.mapping?.value ?? ""}
          placeholder={row.mapping ? "" : "자료에서 미감지 — 직접 입력"}
          onCommit={(next) => onValueChange(row.variable.key, next)}
        />
      ),
    },
    {
      title: "상태",
      width: 100,
      render: (_, row) => statusBadge(row),
    },
    {
      title: "출처",
      width: 100,
      render: (_, row) => {
        const m = row.mapping;
        if (!m) {
          return (
            <Text type="secondary" style={{ fontSize: 12 }}>
              -
            </Text>
          );
        }
        const src = m.source_id ? sourceById.get(m.source_id) ?? null : null;
        return <SourceMetaPopover mapping={m} source={src} />;
      },
    },
    {
      title: "재생성",
      width: 100,
      render: (_, row) => (
        <Button
          size="small"
          type="text"
          icon={<ReloadOutlined />}
          loading={regeneratingKey === row.variable.key}
          disabled={!row.mapping}
          onClick={() => onRegenerate(row.variable.key)}
        >
          Haiku
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 8 }}>
        <Badge
          status={missingCount > 0 ? "error" : "success"}
          text={`전체 ${rows.length}개 · 누락 ${missingCount}개`}
        />
      </Space>
      <Table
        size="small"
        loading={loading}
        rowKey={(r) => r.variable.key}
        dataSource={rows}
        columns={columns}
        pagination={false}
        scroll={{ y: 540 }}
      />
    </div>
  );
}
