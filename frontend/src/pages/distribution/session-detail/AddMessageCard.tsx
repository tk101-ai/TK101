import { Button, Card, Input, InputNumber, Select, Space, Typography } from "antd";
import { PlusOutlined } from "@ant-design/icons";

const { Text } = Typography;
const { TextArea } = Input;

interface AddMessageCardProps {
  senderLabel: string;
  receiverLabel: string;
  addSide: "sender" | "receiver";
  setAddSide: (v: "sender" | "receiver") => void;
  addContent: string;
  setAddContent: (v: string) => void;
  addAfterSec: number;
  setAddAfterSec: (v: number) => void;
  adding: boolean;
  onAdd: () => void;
}

export function AddMessageCard({
  senderLabel,
  receiverLabel,
  addSide,
  setAddSide,
  addContent,
  setAddContent,
  addAfterSec,
  setAddAfterSec,
  adding,
  onAdd,
}: AddMessageCardProps) {
  return (
    <Card title="메시지 추가" size="small" style={{ marginTop: 16 }}>
      <Space direction="vertical" style={{ width: "100%" }} size={8}>
        <Select
          value={addSide}
          onChange={(v) => setAddSide(v)}
          style={{ width: 280 }}
          options={[
            {
              label: `발신: ${senderLabel}`,
              value: "sender",
            },
            {
              label: `수신: ${receiverLabel}`,
              value: "receiver",
            },
          ]}
        />
        <TextArea
          value={addContent}
          onChange={(e) => setAddContent(e.target.value)}
          autoSize={{ minRows: 2, maxRows: 6 }}
          maxLength={4096}
          showCount
          placeholder="추가할 메시지 내용 (맨 끝에 추가됩니다)"
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
            맨 끝에 추가
          </Button>
        </Space>
      </Space>
    </Card>
  );
}
