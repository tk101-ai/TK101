import { Button, Card, Empty, Popconfirm, Timeline } from "antd";
import { DeleteOutlined } from "@ant-design/icons";
import type { MessageItem } from "../../../api/distribution";
import { MessageRow } from "./MessageRow";

interface MessageTimelineProps {
  messages: MessageItem[];
  cumulativeOffsets: number[];
  editingDisabled: boolean;
  showSendState: boolean;
  onSaved: (next: MessageItem) => void;
  onDeleteMessage: (messageId: string) => void;
}

export function MessageTimeline({
  messages,
  cumulativeOffsets,
  editingDisabled,
  showSendState,
  onSaved,
  onDeleteMessage,
}: MessageTimelineProps) {
  return (
    <Card title="메시지 타임라인" size="small">
      {messages.length === 0 ? (
        <Empty description="메시지가 없습니다" />
      ) : (
        <Timeline
          items={messages.map((msg, idx) => ({
            color: msg.status === "sent" ? "green" : msg.status === "failed" ? "red" : "blue",
            children: (
              <div>
                <MessageRow
                  key={msg.id}
                  msg={msg}
                  cumulativeOffset={cumulativeOffsets[idx] ?? 0}
                  onSaved={onSaved}
                  editingDisabled={editingDisabled}
                  showSendState={showSendState}
                />
                {!editingDisabled && (
                  <Popconfirm
                    title="이 메시지를 삭제할까요?"
                    okText="삭제"
                    cancelText="취소"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => {
                      onDeleteMessage(msg.id);
                    }}
                  >
                    <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                      메시지 삭제
                    </Button>
                  </Popconfirm>
                )}
              </div>
            ),
          }))}
        />
      )}
    </Card>
  );
}
