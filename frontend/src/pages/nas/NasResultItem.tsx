import { useState, type ReactNode } from "react";
import { List, message, Space, Tag, Tooltip } from "antd";
import {
  FileOutlined,
  FilePdfOutlined,
  FilePptOutlined,
  FileWordOutlined,
  FileExcelOutlined,
  FileImageOutlined,
} from "@ant-design/icons";
import { downloadNasFile, type NasSearchHit } from "../../api/nas";
import { fileIconType, formatDate, formatFileSize } from "./nasUtils";

interface NasResultItemProps {
  hit: NasSearchHit;
  /** 매칭 하이라이트용 검색어. 비어있으면 하이라이트 미적용. */
  highlight?: string;
}

const SNIPPET_PREVIEW_CHARS = 140;

function pickIcon(mimeType: string | null, fileType: string | null, name?: string | null): ReactNode {
  const kind = fileIconType(mimeType, fileType, name);
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
    case "hwp":
      // 한글 전용 아이콘은 antd에 없어 일반 파일 아이콘 + 한글 브랜드 색(파랑)으로 식별.
      return <FileOutlined style={{ ...baseStyle, color: "#0050b3" }} />;
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

function scoreLabel(score: number): string {
  // 점수 백분율(소수점 0자리). 0~1 + 파일명 가산점 0.2 까지 들어올 수 있어 100% 캡.
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  return `${pct}%`;
}

function escapeRegExp(input: string): string {
  return input.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * 검색어 토큰을 snippet 안에서 <mark>로 감싸 돌려준다.
 * 공백 단위 토큰화. 빈 토큰은 무시. 토큰 1자도 허용(한글 1글자 매칭 케이스).
 */
function highlightSnippet(text: string, query: string | undefined): ReactNode {
  if (!query || !text) return text;
  const tokens = query
    .split(/\s+/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
  if (tokens.length === 0) return text;
  const pattern = new RegExp(`(${tokens.map(escapeRegExp).join("|")})`, "gi");
  const parts = text.split(pattern);
  return parts.map((part, idx) =>
    pattern.test(part) ? (
      <mark
        key={idx}
        style={{ background: "#fff1b8", color: "inherit", padding: "0 2px", borderRadius: 2 }}
      >
        {part}
      </mark>
    ) : (
      <span key={idx}>{part}</span>
    ),
  );
}

export default function NasResultItem({ hit, highlight }: NasResultItemProps) {
  const [expanded, setExpanded] = useState(false);

  const handleOpen = async () => {
    try {
      await downloadNasFile(hit.id, hit.name || "download");
    } catch {
      message.error("파일 다운로드 실패");
    }
  };

  const snippet = hit.snippet ?? "";
  const isLong = snippet.length > SNIPPET_PREVIEW_CHARS;
  const visibleSnippet = expanded || !isLong ? snippet : `${snippet.slice(0, SNIPPET_PREVIEW_CHARS)}…`;

  const toggleExpand = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setExpanded((prev) => !prev);
  };

  return (
    <List.Item
      style={{ cursor: "pointer", padding: "16px 12px" }}
      onClick={handleOpen}
      extra={
        <Tooltip title={`유사도 ${hit.score.toFixed(3)}`}>
          <Tag color={scoreColor(hit.score)} style={{ fontSize: 13, padding: "2px 10px" }}>
            {scoreLabel(hit.score)}
          </Tag>
        </Tooltip>
      }
    >
      <List.Item.Meta
        avatar={pickIcon(hit.mime_type, hit.file_type, hit.name)}
        title={
          <span style={{ fontSize: 15, fontWeight: 600, color: "#1677ff" }}>
            {hit.name}
            {hit.dept ? (
              <Tag color="cyan" style={{ marginLeft: 8, fontWeight: 400 }}>
                {hit.dept}
              </Tag>
            ) : null}
          </span>
        }
        description={
          <div>
            <div style={{ color: "#8c8c8c", fontSize: 12, marginBottom: 6, wordBreak: "break-all" }}>
              {hit.path}
            </div>
            {snippet && (
              <div
                style={{
                  background: "#fafafa",
                  border: "1px solid #f0f0f0",
                  borderRadius: 4,
                  padding: "8px 12px",
                  color: "#595959",
                  fontSize: 13,
                  marginBottom: 6,
                  whiteSpace: expanded ? "pre-wrap" : "normal",
                  wordBreak: "break-word",
                }}
              >
                {highlightSnippet(visibleSnippet, highlight)}
                {isLong && (
                  <>
                    {" "}
                    <button
                      type="button"
                      onClick={toggleExpand}
                      style={{
                        background: "transparent",
                        border: "none",
                        color: "#1677ff",
                        padding: 0,
                        cursor: "pointer",
                        fontSize: 12,
                      }}
                    >
                      {expanded ? "접기" : "더 보기"}
                    </button>
                  </>
                )}
              </div>
            )}
            {(hit.size || hit.mtime) ? (
              <Space size={12} style={{ color: "#8c8c8c", fontSize: 12 }}>
                {hit.size ? <span>{formatFileSize(hit.size)}</span> : null}
                {hit.size && hit.mtime ? <span>·</span> : null}
                {hit.mtime ? <span>수정일 {formatDate(hit.mtime)}</span> : null}
              </Space>
            ) : null}
          </div>
        }
      />
    </List.Item>
  );
}
