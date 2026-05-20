import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Alert, Button, Space, Spin, Tag, Tooltip, message } from "antd";
import {
  CloseOutlined,
  CloudUploadOutlined,
  PictureOutlined,
} from "@ant-design/icons";
import {
  attachmentFileUrl,
  classifyAttachment,
  deleteAttachment,
  uploadAttachment,
  MAX_ATTACHMENT_BYTES,
  type PlaygroundAttachment,
} from "../../api/playground";

interface BaseImagePickerProps {
  value: PlaygroundAttachment | null;
  onChange: (next: PlaygroundAttachment | null) => void;
  /** 베이스 이미지가 백엔드 시점에서 어떻게 처리되는지 사용자에게 안내. */
  pendingNotice?: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * 미디어 생성 패널용 베이스 이미지 1장 픽커.
 *
 * - 클릭 또는 드래그앤드롭으로 이미지 1장 업로드 (이미지만 허용)
 * - 업로드 성공 시 썸네일 + 파일명 + 제거 버튼
 * - pendingNotice 가 있으면 노란 안내 alert (텐센트 spec 대기 등)
 */
export default function BaseImagePicker({
  value,
  onChange,
  pendingNotice,
}: BaseImagePickerProps) {
  const [uploading, setUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const dragCounter = useRef(0);

  const upload = async (file: File) => {
    if (file.size > MAX_ATTACHMENT_BYTES) {
      message.warning(
        `파일이 너무 큽니다 (최대 ${MAX_ATTACHMENT_BYTES / (1024 * 1024)}MB)`,
      );
      return;
    }
    const kind = classifyAttachment(file);
    if (kind !== "image") {
      message.warning("베이스로는 이미지 파일만 사용할 수 있습니다");
      return;
    }
    setUploading(true);
    try {
      // 이전 베이스가 있으면 먼저 제거.
      if (value) {
        try {
          await deleteAttachment(value.id);
        } catch {
          // 무시 — 새 베이스로 교체.
        }
      }
      const att = await uploadAttachment(file);
      onChange(att);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "업로드 실패";
      message.error(msg);
    } finally {
      setUploading(false);
    }
  };

  const onFilePicked = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) await upload(file);
  };

  const onDragEnter = (e: DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    dragCounter.current += 1;
    setIsDragging(true);
  };
  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };
  const onDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) await upload(file);
  };

  const remove = async () => {
    const target = value;
    onChange(null);
    if (target) {
      try {
        await deleteAttachment(target.id);
      } catch {
        // ignore
      }
    }
  };

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={onFilePicked}
      />

      {pendingNotice && (
        <Alert
          type="warning"
          showIcon
          message={pendingNotice}
          style={{ marginBottom: 8, fontSize: 12 }}
        />
      )}

      {value ? (
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <img
            src={attachmentFileUrl(value.id)}
            alt={value.filename}
            style={{
              width: 88,
              height: 88,
              objectFit: "cover",
              borderRadius: 6,
              border: "1px solid rgba(0,0,0,0.08)",
            }}
          />
          <Space direction="vertical" size={2} style={{ flex: 1, minWidth: 0 }}>
            <Tag color="blue" icon={<PictureOutlined />} style={{ marginRight: 0 }}>
              {value.filename}
            </Tag>
            <span style={{ fontSize: 11, color: "rgba(0,0,0,0.5)" }}>
              {formatSize(value.size_bytes)}
            </span>
            <Button
              size="small"
              danger
              icon={<CloseOutlined />}
              onClick={() => {
                void remove();
              }}
            >
              제거
            </Button>
          </Space>
        </div>
      ) : (
        <div
          onClick={() => inputRef.current?.click()}
          onDragEnter={onDragEnter}
          onDragLeave={onDragLeave}
          onDragOver={onDragOver}
          onDrop={onDrop}
          style={{
            cursor: "pointer",
            border: `2px dashed ${isDragging ? "#1677ff" : "rgba(0,0,0,0.15)"}`,
            background: isDragging ? "rgba(22,119,255,0.06)" : "rgba(0,0,0,0.02)",
            borderRadius: 8,
            padding: 18,
            textAlign: "center",
            color: isDragging ? "#1677ff" : "rgba(0,0,0,0.55)",
            fontSize: 12,
            transition: "all 120ms ease",
          }}
        >
          {uploading ? (
            <Space>
              <Spin size="small" />
              <span>업로드 중…</span>
            </Space>
          ) : (
            <Space direction="vertical" size={4}>
              <CloudUploadOutlined style={{ fontSize: 22 }} />
              <div>베이스 이미지 — 클릭 또는 드래그앤드롭</div>
              <Tooltip title="PNG / JPG / WebP, 20MB 이하">
                <span style={{ fontSize: 11, opacity: 0.65 }}>
                  PNG · JPG · WebP / 20MB
                </span>
              </Tooltip>
            </Space>
          )}
        </div>
      )}
    </div>
  );
}
