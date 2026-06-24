import { Button, Card, Input, InputNumber, Select, Space, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";

const { Text } = Typography;
const { TextArea } = Input;

interface AddMessageCardProps {
  senderLabel: string;
  receiverLabel: string;
  messageCount: number;
  addSide: "sender" | "receiver";
  setAddSide: (v: "sender" | "receiver") => void;
  addContent: string;
  setAddContent: (v: string) => void;
  addAfterSec: number;
  setAddAfterSec: (v: number) => void;
  addPosition: number | null;
  setAddPosition: (v: number | null) => void;
  adding: boolean;
  onAdd: () => void;
}

export function AddMessageCard({
  senderLabel,
  receiverLabel,
  messageCount,
  addSide,
  setAddSide,
  addContent,
  setAddContent,
  addAfterSec,
  setAddAfterSec,
  addPosition,
  setAddPosition,
  adding,
  onAdd,
}: AddMessageCardProps) {
  const positionOptions = [
    { label: "맨 끝", value: "end" },
    { label: "맨 앞", value: "0" },
    ...Array.from({ length: messageCount }, (_, index) => ({
      label: String(index + 1) + "번 메시지 뒤",
      value: String(index + 1),
    })),
  ];

  return (
    <Card title="메시지 추가" size="small" style={{ marginTop: 16 }}>
      <Space direction="vertical" style={{ width: "100%" }} size={8}>
        <Space wrap>
          <Select
            value={addSide}
            onChange={(v) => setAddSide(v)}
            style={{ width: 280 }}
            options={[
              {
                label: "발송: " + senderLabel,
                value: "sender",
              },
              {
                label: "상대: " + receiverLabel,
                value: "receiver",
              },
            ]}
          />
          <Select
            value={addPosition === null ? "end" : String(addPosition)}
            onChange={(value) => {
              setAddPosition(value === "end" ? null : Number(value));
            }}
            style={{ width: 180 }}
            options={positionOptions}
          />
        </Space>
        <TextArea
          value={addContent}
          onChange={(e) => setAddContent(e.target.value)}
          autoSize={{ minRows: 2, maxRows: 6 }}
          maxLength={4096}
          showCount
          placeholder="추가할 메시지 내용"
        />
        <Space>
          <Text type="secondary">이전 메시지 후 대기(초):</Text>
          <InputNumber
            min={0}
            max={86400}
            value={addAfterSec}
            onChange={(v) => setAddAfterSec(Number(v) || 0)}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            loading={adding}
            onClick={() => {
              onAdd();
            }}
          >
            추가
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
