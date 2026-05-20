import {
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
} from "react";
import { Alert, Button, Input, Space, Spin, Tag, Tooltip } from "antd";
import {
  CloseOutlined,
  FileOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileWordOutlined,
  PaperClipOutlined,
  PictureOutlined,
  PlusOutlined,
  SendOutlined,
} from "@ant-design/icons";
import {
  getVisionModels,
  type PlaygroundAttachment,
} from "../../api/playground";

interface ChatInputBarProps {
  onSend: (text: string, attachmentIds: string[]) => void;
  onNewChat: () => void;
  sending: boolean;
  disabled?: boolean;
  /** 현재 세션의 모델 ID. vision 미지원 모델 + 이미지 첨부 시 경고. */
  model: string;
  /** 첨부 상태 — LlmChatPanel 의 useChatAttachments 가 소유. */
  attachments: PlaygroundAttachment[];
  uploading: boolean;
  onAddFiles: (files: File[]) => Promise<void> | void;
  onRemoveAttachment: (id: string) => void | Promise<void>;
  onAfterSend: () => void;
}

const KIND_ICON: Record<PlaygroundAttachment["kind"], ReactNode> = {
  image: <PictureOutlined />,
  pdf: <FilePdfOutlined />,
  text: <FileTextOutlined />,
  docx: <FileWordOutlined />,
};

const KIND_COLOR: Record<PlaygroundAttachment["kind"], string> = {
  image: "blue",
  pdf: "red",
  text: "green",
  docx: "geekblue",
};

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * 하단 입력바 (2026-05-20: 파일 첨부 지원, 상태는 부모가 소유).
 *
 * - "New Chat" 버튼: 세션 초기화
 * - 클립 아이콘: 파일 picker (드래그앤드롭은 부모 LlmChatPanel 의 카드 전체에서)
 * - 첨부 칩 + 개별 삭제
 * - 이미지 첨부 + vision 미지원 모델 = 경고 노출
 * - Enter 전송, Shift+Enter 줄바꿈
 */
export default function ChatInputBar({
  onSend,
  onNewChat,
  sending,
  disabled,
  model,
  attachments,
  uploading,
  onAddFiles,
  onRemoveAttachment,
  onAfterSend,
}: ChatInputBarProps) {
  const [text, setText] = useState("");
  const [visionModels, setVisionModels] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    getVisionModels()
      .then((ids) => {
        if (!cancelled) setVisionModels(new Set(ids));
      })
      .catch(() => {
        // vision 모델 목록을 못 받아오면 경고 비활성화 — 업로드는 그대로 가능.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hasImageAttachment = attachments.some((a) => a.kind === "image");
  const visionSupported = visionModels.has(model);
  const showVisionWarning =
    hasImageAttachment && visionModels.size > 0 && !visionSupported;

  const onFilePicked = async (e: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    e.target.value = ""; // 같은 파일 재선택 허용.
    await onAddFiles(files);
  };

  const flush = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    const ids = attachments.map((a) => a.id);
    onSend(trimmed, ids);
    setText("");
    onAfterSend(); // 전송 후 첨부 비움 (부모에서 처리).
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
        background: "#fff",
      }}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,application/pdf,text/*,.md,.csv,.json,.log,.py,.ts,.tsx,.js,.html,.xml,.yaml,.yml,.docx"
        style={{ display: "none" }}
        onChange={onFilePicked}
      />

      {showVisionWarning && (
        <Alert
          type="warning"
          showIcon
          message={`현재 모델(${model})은 이미지 입력을 지원하지 않습니다. 이미지 첨부는 안내 텍스트로만 전달됩니다.`}
          style={{ marginBottom: 8 }}
        />
      )}

      {attachments.length > 0 && (
        <Space size={[6, 6]} wrap style={{ marginBottom: 8 }}>
          {attachments.map((a) => (
            <Tag
              key={a.id}
              color={KIND_COLOR[a.kind]}
              icon={KIND_ICON[a.kind] ?? <FileOutlined />}
              closable
              closeIcon={<CloseOutlined />}
              onClose={(e) => {
                e.preventDefault();
                void onRemoveAttachment(a.id);
              }}
              style={{ padding: "4px 8px", fontSize: 12 }}
            >
              {a.filename}
              <span style={{ marginLeft: 6, opacity: 0.7 }}>
                {formatSize(a.size_bytes)}
              </span>
            </Tag>
          ))}
        </Space>
      )}

      <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
        <Button
          icon={<PlusOutlined />}
          onClick={onNewChat}
          disabled={sending}
          size="middle"
        >
          New Chat
        </Button>
        <Tooltip title="파일 첨부 — 이미지/PDF/텍스트/DOCX (20MB 이하)">
          <Button
            icon={uploading ? <Spin size="small" /> : <PaperClipOutlined />}
            onClick={() => fileInputRef.current?.click()}
            disabled={sending || uploading}
          />
        </Tooltip>
        <Input.TextArea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="메시지를 입력하세요 — Enter 전송, Shift+Enter 줄바꿈. 파일은 클립 또는 채팅 영역에 드래그앤드롭"
          autoSize={{ minRows: 1, maxRows: 6 }}
          disabled={disabled || sending}
          style={{ flex: 1, fontSize: 13 }}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={flush}
          loading={sending}
          disabled={disabled || (!text.trim() && attachments.length === 0)}
        >
          전송
        </Button>
      </div>
    </div>
  );
}
