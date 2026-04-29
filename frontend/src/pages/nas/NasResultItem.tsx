import { List, message, Space, Tag } from "antd";
import {
  FileOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FileImageOutlined,
} from "@ant-design/icons";
import type { ReactNode } from "react";
import { downloadNasFile, type NasSearchHit } from "../../api/nas";
import { fileIconType, formatDate, formatFileSize } from "./nasUtils";

interface NasResultItemProps {
  hit: NasSearchHit;
}

function pickIcon(mimeType: string, fileType: string): ReactNode {
  const kind = fileIconType(mimeType, fileType);
  const baseStyle = { fontSize: 28 };
  switch (kind) {
    case "pdf":
      return <FilePdfOutlined style={{ ...baseStyle, color: "#cf1322" }} />;
    case "doc":
      return <FileWordOutlined style={{ ...baseStyle, color: "#1677ff" }} />;
    case "ppt":
      return <FilePptOutlined style={{ ...baseStyle, color: "#d4380d" }} />;
    case "xls":
      return <FileExcelOutlined style={{ ...baseStyle, color: "#389e0d" }} />;
    case "image":
      return <FileImageOutlined style={{ ...baseStyle, color: "#722ed1" }} />;
    default:
      return <FileOutlined style={{ ...baseStyle, color: "#8c8c8c" }} />;
  }
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "green";
  if (score >= 0.5) return "blue";
  if (score >= 0.3) return "orange";
  return "default";
}

export default function NasResultItem({ hit }: NasResultItemProps) {
  const handleOpen = async () => {
    try {
      await downloadNasFile(hit.id, hit.name || "download");
    } catch {
      message.error("파일 다운로드 실패");
    }
  };

  return (
    <List.Item
      style={{ cursor: "pointer", padding: "16px 12px" }}
      onClick={handleOpen}
      extra={
        <Tag color={scoreColor(hit.score)} style={{ fontSize: 13, padding: "2px 10px" }}>
          {hit.score.toFixed(2)}
        </Tag>
      }
    >
      <List.Item.Meta
        avatar={pickIcon(hit.mime_type, hit.file_type)}
        title={
          <span style={{ fontSize: 15, fontWeight: 600, color: "#1677ff" }}>{hit.name}</span>
        }
        description={
          <div>
            <div style={{ color: "#8c8c8c", fontSize: 12, marginBottom: 6, wordBreak: "break-all" }}>
              {hit.path}
            </div>
            {hit.snippet && (
              <div
                style={{
                  background: "#fafafa",
                  border: "1px solid #f0f0f0",
                  borderRadius: 4,
                  padding: "8px 12px",
                  color: "#595959",
                  fontSize: 13,
                  marginBottom: 6,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {hit.snippet}
              </div>
            )}
            <Space size={12} style={{ color: "#8c8c8c", fontSize: 12 }}>
              <span>{formatFileSize(hit.size)}</span>
              <span>·</span>
              <span>수정일 {formatDate(hit.mtime)}</span>
            </Space>
          </div>
        }
      />
    </List.Item>
  );
}
