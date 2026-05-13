import { useState, type KeyboardEvent } from "react";
import { Button, Input, Tooltip } from "antd";
import { PaperClipOutlined, PlusOutlined, SendOutlined } from "@ant-design/icons";

interface ChatInputBarProps {
  onSend: (text: string) => void;
  onNewChat: () => void;
  sending: boolean;
  disabled?: boolean;
}

/**
 * 하단 입력바.
 *
 * - "New Chat" 버튼: 세션 초기화
 * - 첨부 클립 아이콘: Phase 4까지 disabled (멀티모달 입력)
 * - Enter 전송, Shift+Enter 줄바꿈
 */
export default function ChatInputBar({
  onSend,
  onNewChat,
  sending,
  disabled,
}: ChatInputBarProps) {
  const [text, setText] = useState("");

  const flush = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSend(trimmed);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      flush();
    }
  };

  return (
    <div
      style={{
        borderTop: "1px solid rgba(0,0,0,0.08)",
        padding: "12px 24px",
        display: "flex",
        alignItems: "flex-end",
        gap: 8,
        background: "#fff",
      }}
    >
      <Button
        icon={<PlusOutlined />}
        onClick={onNewChat}
        disabled={sending}
        size="middle"
      >
        New Chat
      </Button>
      <Tooltip title="첨부는 Phase 4(이미지 입력)에서 활성화됩니다">
        <Button icon={<PaperClipOutlined />} disabled />
      </Tooltip>
      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="메시지를 입력하세요 — Enter 전송, Shift+Enter 줄바꿈"
        autoSize={{ minRows: 1, maxRows: 6 }}
        disabled={disabled || sending}
        style={{ flex: 1, fontSize: 13 }}
      />
      <Button
        type="primary"
        icon={<SendOutlined />}
        onClick={flush}
        loading={sending}
        disabled={disabled || !text.trim()}
      >
        전송
      </Button>
    </div>
  );
}
