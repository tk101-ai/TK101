import { Button, Input, Select, Space, Switch, Table, Tag } from "antd";
import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { FormVariable, FormVariableType } from "../../api/forms";

interface VariableEditorProps {
  variables: FormVariable[];
  onChange: (next: FormVariable[]) => void;
  readOnly?: boolean;
}

const TYPE_OPTIONS: { value: FormVariableType; label: string }[] = [
  { value: "text", label: "텍스트" },
  { value: "number", label: "숫자" },
  { value: "date", label: "날짜" },
  { value: "enum", label: "선택" },
  { value: "checkbox", label: "체크박스" },
  { value: "table_row", label: "표 행" },
  { value: "image", label: "이미지" },
];

function confidenceTag(c?: number) {
  if (c === undefined || c === null) return <Tag color="default">미감지</Tag>;
  if (c >= 0.8) return <Tag color="green">{c.toFixed(2)}</Tag>;
  if (c >= 0.5) return <Tag color="orange">{c.toFixed(2)}</Tag>;
  return <Tag color="red">{c.toFixed(2)}</Tag>;
}

export default function VariableEditor({
  variables,
  onChange,
  readOnly = false,
}: VariableEditorProps) {
  const updateAt = (index: number, patch: Partial<FormVariable>) => {
    const next = variables.map((v, i) => (i === index ? { ...v, ...patch } : v));
    onChange(next);
  };

  const removeAt = (index: number) => {
    onChange(variables.filter((_, i) => i !== index));
  };

  const addNew = () => {
    const key = `custom_${variables.length + 1}`;
    onChange([
      ...variables,
      { key, label: "사용자 정의 변수", type: "text", required: false, confidence: 1.0 },
    ]);
  };

  const columns: ColumnsType<FormVariable & { __index: number }> = [
    {
      title: "키",
      dataIndex: "key",
      width: 160,
      render: (_, row) => (
        <Input
          size="small"
          value={row.key}
          disabled={readOnly}
          onChange={(e) => updateAt(row.__index, { key: e.target.value })}
        />
      ),
    },
    {
      title: "라벨",
      dataIndex: "label",
      render: (_, row) => (
        <Input
          size="small"
          value={row.label}
          disabled={readOnly}
          onChange={(e) => updateAt(row.__index, { label: e.target.value })}
        />
      ),
    },
    {
      title: "타입",
      dataIndex: "type",
      width: 130,
      render: (_, row) => (
        <Select
          size="small"
          value={row.type}
          disabled={readOnly}
          onChange={(v) => updateAt(row.__index, { type: v })}
          options={TYPE_OPTIONS}
          style={{ width: "100%" }}
        />
      ),
    },
    {
      title: "필수",
      dataIndex: "required",
      width: 70,
      render: (_, row) => (
        <Switch
          size="small"
          disabled={readOnly}
          checked={!!row.required}
          onChange={(v) => updateAt(row.__index, { required: v })}
        />
      ),
    },
    {
      title: "감지 신뢰도",
      dataIndex: "confidence",
      width: 110,
      render: (_, row) => confidenceTag(row.confidence),
    },
    {
      title: "위치",
      dataIndex: "location",
      width: 110,
      render: (v) => <span style={{ color: "#8c8c8c", fontSize: 12 }}>{v ?? "-"}</span>,
    },
    {
      title: "",
      width: 50,
      render: (_, row) =>
        readOnly ? null : (
          <Button
            size="small"
            type="text"
            danger
            icon={<DeleteOutlined />}
            onClick={() => removeAt(row.__index)}
          />
        ),
    },
  ];

  const dataSource = variables.map((v, i) => ({ ...v, __index: i }));

  return (
    <div>
      <Table
        size="small"
        rowKey={(r) => `${r.__index}-${r.key}`}
        dataSource={dataSource}
        columns={columns}
        pagination={false}
        scroll={{ y: 480 }}
      />
      {!readOnly && (
        <Space style={{ marginTop: 12 }}>
          <Button icon={<PlusOutlined />} onClick={addNew}>
            변수 수기 추가
          </Button>
          <span style={{ color: "#8c8c8c", fontSize: 12 }}>
            총 {variables.length}개 변수 · 자동 감지 누락분은 수기 등록 가능
          </span>
        </Space>
      )}
    </div>
  );
}
