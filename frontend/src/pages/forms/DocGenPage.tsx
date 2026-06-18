import { useState } from "react";
import {
  Button,
  Card,
  Input,
  List,
  message,
  Segmented,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import { DownloadOutlined, FileSearchOutlined, ThunderboltOutlined } from "@ant-design/icons";
import {
  downloadGeneratedDocx,
  generateDocument,
  type DocGenResponse,
  type DocType,
} from "../../api/docgen";

const { Text, Paragraph, Title } = Typography;
const DOC_TYPES: DocType[] = ["제안서", "계획서", "보고서", "일반"];

/**
 * 요구 기반 문서 생성 (T5 확장).
 * 주제 입력 → NAS 벡터검색(RAG) → Claude 구조화 초안 → .docx 다운로드.
 */
export default function DocGenPage() {
  const [topic, setTopic] = useState("");
  const [docType, setDocType] = useState<DocType>("제안서");
  const [useNas, setUseNas] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocGenResponse | null>(null);

  const handleGenerate = async () => {
    const t = topic.trim();
    if (t.length < 2) {
      message.warning("작성 요구/주제를 입력하세요");
      return;
    }
    setBusy(true);
    try {
      const res = await generateDocument({ topic: t, doc_type: docType, use_nas: useNas });
      setResult(res);
      message.success(`초안 생성 완료 (참고 ${res.sources.length}건 · $${res.cost_usd.toFixed(4)})`);
    } catch {
      message.error("문서 생성 실패");
    } finally {
      setBusy(false);
    }
  };

  const handleDownload = async () => {
    if (!result) return;
    try {
      await downloadGeneratedDocx(result.title, result.sections);
    } catch {
      message.error("docx 다운로드 실패");
    }
  };

  return (
    <div style={{ maxWidth: 1080 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
          문서 생성{" "}
          <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
            요구 기반 · RAG 초안
          </Text>
        </h2>
        <Text type="secondary">
          주제를 입력하면 회사 NAS 자료(벡터검색)를 참고해 제안서·계획서 초안을 작성합니다.
        </Text>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space direction="vertical" style={{ width: "100%" }} size={12}>
          <Space wrap>
            <Segmented
              options={DOC_TYPES}
              value={docType}
              onChange={(v) => setDocType(v as DocType)}
            />
            <Space size={6}>
              <Switch checked={useNas} onChange={setUseNas} size="small" />
              <Text type="secondary" style={{ fontSize: 12 }}>
                <FileSearchOutlined /> NAS 자료 참고(RAG)
              </Text>
            </Space>
          </Space>
          <Input.TextArea
            rows={4}
            placeholder="예: 신세계백화점 대상 중국 SNS 운영 대행 제안서를 작성해줘. 운영 채널과 견적 흐름 포함."
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            disabled={busy}
          />
          <Button
            type="primary"
            icon={<ThunderboltOutlined />}
            onClick={handleGenerate}
            loading={busy}
            disabled={topic.trim().length < 2}
          >
            초안 생성
          </Button>
        </Space>
      </Card>

      {result && (
        <Card
          title={<Title level={5} style={{ margin: 0 }}>{result.title}</Title>}
          extra={
            <Button icon={<DownloadOutlined />} onClick={handleDownload}>
              .docx 다운로드
            </Button>
          }
        >
          {result.sources.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>참고 자료: </Text>
              {result.sources.map((s) => (
                <Tag key={s.path} color="blue" title={s.path} style={{ marginBottom: 4 }}>
                  …{s.path.slice(-28)} ({s.score.toFixed(2)})
                </Tag>
              ))}
            </div>
          )}
          <List
            dataSource={result.sections}
            renderItem={(s) => (
              <List.Item style={{ display: "block" }}>
                <Title level={5} style={{ marginTop: 0 }}>{s.heading}</Title>
                <Paragraph style={{ whiteSpace: "pre-wrap", marginBottom: 0 }}>{s.body}</Paragraph>
              </List.Item>
            )}
          />
        </Card>
      )}
    </div>
  );
}
