import { Popover, Tag, Typography } from "antd";
import { InfoCircleOutlined } from "@ant-design/icons";
import type { FormDataSource, FormMapping } from "../../api/forms";

const { Text, Paragraph } = Typography;

interface SourceMetaPopoverProps {
  mapping: FormMapping;
  source: FormDataSource | null;
}

function kindLabel(kind: FormDataSource["kind"] | undefined): string {
  switch (kind) {
    case "nas_file":
      return "NAS 파일";
    case "user_upload":
      return "사용자 업로드";
    case "user_input":
      return "사용자 직접 입력";
    case "web_search":
      return "웹 검색 (v2)";
    default:
      return "미지정";
  }
}

function confColor(c: number | null): string {
  if (c === null) return "default";
  if (c >= 0.8) return "green";
  if (c >= 0.5) return "orange";
  return "red";
}

/**
 * 매핑 옆 "출처" 1클릭 펼쳐보기 — NFR-04 환각 방어 #5.
 * source 가 null 인 경우 (사용자 직접 입력 / 미채움) 도 명확히 표시한다.
 */
export default function SourceMetaPopover({ mapping, source }: SourceMetaPopoverProps) {
  const content = (
    <div style={{ maxWidth: 420 }}>
      <div style={{ marginBottom: 8 }}>
        <Tag color={confColor(mapping.llm_confidence)}>
          신뢰도 {mapping.llm_confidence === null ? "—" : mapping.llm_confidence.toFixed(2)}
        </Tag>
        <Tag>{kindLabel(source?.kind)}</Tag>
      </div>
      {source ? (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            자료 경로
          </Text>
          <Paragraph
            style={{ fontSize: 12, marginTop: 2, marginBottom: 8, wordBreak: "break-all" }}
          >
            {source.upload_path ?? source.nas_file_id ?? source.display_name ?? "-"}
          </Paragraph>
        </>
      ) : (
        <Paragraph style={{ fontSize: 12, marginBottom: 8 }}>
          출처 자료 없음 — <Text strong>사용자 입력 또는 미채움</Text>
        </Paragraph>
      )}
      {mapping.source_excerpt && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            발췌문
          </Text>
          <Paragraph
            style={{
              background: "#fafafa",
              border: "1px solid #f0f0f0",
              borderRadius: 4,
              padding: 8,
              fontSize: 12,
              marginTop: 2,
              marginBottom: 8,
              whiteSpace: "pre-wrap",
            }}
          >
            {mapping.source_excerpt}
          </Paragraph>
        </>
      )}
      {mapping.reasoning && (
        <>
          <Text type="secondary" style={{ fontSize: 12 }}>
            매핑 근거 (LLM)
          </Text>
          <Paragraph style={{ fontSize: 12, marginTop: 2, marginBottom: 0 }}>
            {mapping.reasoning}
          </Paragraph>
        </>
      )}
    </div>
  );

  return (
    <Popover content={content} title="출처" trigger="click" placement="leftTop">
      <a style={{ fontSize: 12 }}>
        <InfoCircleOutlined /> 출처
      </a>
    </Popover>
  );
}
