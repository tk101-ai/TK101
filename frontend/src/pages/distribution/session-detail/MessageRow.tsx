import { useState } from "react";
import { Button, Input, Space, Tag, Typography, message } from "antd";
import { EditOutlined, SaveOutlined } from "@ant-design/icons";
import {
  MESSAGE_STATUS_LABEL,
  MESSAGE_STATUS_TAG_COLOR,
  SEND_STATE_LABEL,
  SEND_STATE_TAG_COLOR,
  updateMessage,
  type MessageItem,
} from "../../../api/distribution";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { formatCumulativeOffset, formatDateTime } from "./formatters";
import { TimingEditor } from "./TimingEditor";
import { AttachmentBlock } from "./AttachmentBlock";

const { Text } = Typography;
const { TextArea } = Input;

interface MessageRowProps {
  msg: MessageItem;
  cumulativeOffset: number;
  onSaved: (next: MessageItem) => void;
  editingDisabled: boolean;
  /** 예약 세션 여부 — true 면 워커 송신 상태(send_state)를 읽기 전용 노출. */
  showSendState: boolean;
}

export function MessageRow({
  msg,
  cumulativeOffset,
  onSaved,
  editingDisabled,
  showSendState,
}: MessageRowProps) {
  const [editing, setEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>("");
  const [saving, setSaving] = useState<boolean>(false);

  const display = msg.edited_content ?? msg.content;

  const startEdit = () => {
    setDraft(display);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft("");
  };

  const submitEdit = async () => {
    const trimmed = draft.trim();
    if (trimmed.length === 0) {
      message.warning("메시지 본문은 비울 수 없습니다.");
      return;
    }
    setSaving(true);
    try {
      const next = await updateMessage(msg.id, trimmed);
      message.success(`메시지 #${msg.order_index + 1} 저장됨`);
      onSaved(next);
      setEditing(false);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "메시지 저장 실패"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ marginBottom: 4 }}>
      <Space size={6} wrap style={{ marginBottom: 4 }}>
        <Text strong>{msg.sender_account_label}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatCumulativeOffset(cumulativeOffset)}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          이전 메시지로부터 +{msg.send_after_sec}s
        </Text>
        <TimingEditor msg={msg} disabled={editingDisabled} onUpdated={onSaved} />
        <Tag color={MESSAGE_STATUS_TAG_COLOR[msg.status]}>
          {MESSAGE_STATUS_LABEL[msg.status]}
        </Tag>
        {showSendState && (
          <Tag color={SEND_STATE_TAG_COLOR[msg.send_state]}>
            {SEND_STATE_LABEL[msg.send_state]}
          </Tag>
        )}
        {showSendState && msg.scheduled_send_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            예정: {formatDateTime(msg.scheduled_send_at)}
          </Text>
        )}
        {msg.user_edited && (
          <Tag color="purple" icon={<EditOutlined />}>
            수정됨
          </Tag>
        )}
        {msg.sent_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            송신: {formatDateTime(msg.sent_at)}
          </Text>
        )}
      </Space>

      {editing ? (
        <div>
          <TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 8 }}
            maxLength={4096}
            showCount
            disabled={saving}
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={() => {
                void submitEdit();
              }}
            >
              저장
            </Button>
            <Button size="small" onClick={cancelEdit} disabled={saving}>
              취소
            </Button>
          </Space>
        </div>
      ) : (
        <div
          onClick={() => {
            if (!editingDisabled) startEdit();
          }}
          style={{
            padding: "8px 12px",
            background: msg.user_edited ? "#f9f0ff" : "#fafafa",
            borderRadius: 6,
            border: "1px solid #f0f0f0",
            whiteSpace: "pre-wrap",
            cursor: editingDisabled ? "default" : "text",
          }}
          title={editingDisabled ? "송신 완료 상태에서는 편집할 수 없습니다" : "클릭하여 편집"}
        >
          {display}
        </div>
      )}
      <AttachmentBlock msg={msg} disabled={editingDisabled} onChanged={onSaved} />
    </div>
  );
}
