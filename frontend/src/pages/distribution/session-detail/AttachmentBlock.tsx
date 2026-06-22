import { useState } from "react";
import { Button, Popconfirm, Typography, message } from "antd";
import { DeleteOutlined, FileOutlined, PaperClipOutlined } from "@ant-design/icons";
import {
  deleteMessageAttachment,
  uploadMessageAttachment,
  type MessageItem,
} from "../../../api/distribution";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { ATTACHMENT_ACCEPT, formatBytes } from "./formatters";

const { Text } = Typography;

interface AttachmentBlockProps {
  msg: MessageItem;
  disabled: boolean;
  onChanged: (next: MessageItem) => void;
}

export function AttachmentBlock({ msg, disabled, onChanged }: AttachmentBlockProps) {
  const [busy, setBusy] = useState<boolean>(false);
  const inputId = `att-${msg.id}`;

  const handleFile = async (file: File) => {
    setBusy(true);
    try {
      const next = await uploadMessageAttachment(msg.id, file);
      message.success(`첨부 업로드: ${file.name}`);
      onChanged(next);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "첨부 업로드 실패"));
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async () => {
    setBusy(true);
    try {
      const next = await deleteMessageAttachment(msg.id);
      message.success("첨부 제거됨");
      onChanged(next);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "첨부 제거 실패"));
    } finally {
      setBusy(false);
    }
  };

  if (msg.attachment_url) {
    return (
      <div style={{ marginTop: 6 }}>
        {msg.attachment_kind === "image" ? (
          <a href={msg.attachment_url} target="_blank" rel="noreferrer">
            <img
              src={msg.attachment_url}
              alt={msg.attachment_filename ?? "첨부 이미지"}
              style={{
                maxWidth: 180,
                maxHeight: 180,
                border: "1px solid #f0f0f0",
                borderRadius: 6,
                display: "block",
              }}
            />
          </a>
        ) : (
          <a
            href={msg.attachment_url}
            target="_blank"
            rel="noreferrer"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "6px 10px",
              border: "1px solid #d9d9d9",
              borderRadius: 6,
              background: "#fafafa",
            }}
          >
            <FileOutlined />
            <span>{msg.attachment_filename ?? "첨부 파일"}</span>
          </a>
        )}
        {!disabled && (
          <Popconfirm
            title="첨부를 제거하시겠습니까?"
            okText="제거"
            cancelText="취소"
            onConfirm={() => {
              void handleRemove();
            }}
          >
            <Button
              size="small"
              type="text"
              danger
              icon={<DeleteOutlined />}
              loading={busy}
              style={{ marginTop: 4 }}
            >
              첨부 제거
            </Button>
          </Popconfirm>
        )}
      </div>
    );
  }

  if (disabled) return null;

  return (
    <div style={{ marginTop: 6 }}>
      <input
        id={inputId}
        type="file"
        accept={ATTACHMENT_ACCEPT}
        style={{ display: "none" }}
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) {
            if (f.size > 200 * 1024 * 1024) {
              message.warning(
                `파일이 너무 큽니다 (${formatBytes(f.size)}). 최대 200MB.`,
              );
            } else {
              void handleFile(f);
            }
          }
          e.target.value = "";
        }}
      />
      <Button
        size="small"
        icon={<PaperClipOutlined />}
        loading={busy}
        onClick={() => document.getElementById(inputId)?.click()}
      >
        파일 첨부
      </Button>
      <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
        이미지·PDF·엑셀·한글 등 (최대 200MB)
      </Text>
    </div>
  );
}
