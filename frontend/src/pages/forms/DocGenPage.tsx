import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Input,
  List,
  message,
  Popconfirm,
  Segmented,
  Space,
  Switch,
  Tag,
  Typography,
} from "antd";
import {
  AuditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileSearchOutlined,
  PlusOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  downloadGeneratedDocx,
  downloadGeneratedPptx,
  generateDocument,
  regenerateSection,
  reviewDocument,
  type DocGenResponse,
  type DocReviewResponse,
  type DocSection,
  type DocType,
} from "../../api/docgen";

const { Text } = Typography;
const DOC_TYPES: DocType[] = ["제안서", "계획서", "보고서", "일반"];

/**
 * 요구 기반 문서 생성 (T5 확장).
 * 주제 → NAS RAG → Claude 초안 → 인라인 편집/섹션 재생성 → docx/PPT 다운로드.
 */
export default function DocGenPage() {
  const [topic, setTopic] = useState("");
  const [docType, setDocType] = useState<DocType>("제안서");
  const [useNas, setUseNas] = useState(true);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocGenResponse | null>(null);

  // 생성 결과를 편집 가능한 상태로 보관(다운로드·재생성은 이 상태 기준).
  const [title, setTitle] = useState("");
  const [sections, setSections] = useState<DocSection[]>([]);
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({});
  const [regenIdx, setRegenIdx] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState<DocReviewResponse | null>(null);

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
      setTitle(res.title);
      setSections(res.sections);
      setFeedbacks({});
      setReview(null);
      message.success(`초안 생성 완료 (참고 ${res.sources.length}건 · $${res.cost_usd.toFixed(4)})`);
    } catch {
      message.error("문서 생성 실패");
    } finally {
      setBusy(false);
    }
  };

  const updateSection = (i: number, patch: Partial<DocSection>) =>
    setSections((prev) => prev.map((s, idx) => (idx === i ? { ...s, ...patch } : s)));

  const deleteSection = (i: number) =>
    setSections((prev) => prev.filter((_, idx) => idx !== i));

  const addSection = () =>
    setSections((prev) => [...prev, { heading: "새 섹션", body: "" }]);

  const handleRegenerate = async (i: number) => {
    setRegenIdx(i);
    try {
      const res = await regenerateSection({
        topic: topic.trim(),
        doc_type: docType,
        heading: sections[i].heading,
        current_body: sections[i].body,
        feedback: feedbacks[i] ?? "",
        use_nas: useNas,
      });
      updateSection(i, res.section);
      setFeedbacks((prev) => ({ ...prev, [i]: "" }));
      message.success(`섹션 재생성 완료 ($${res.cost_usd.toFixed(4)})`);
    } catch {
      message.error("섹션 재생성 실패");
    } finally {
      setRegenIdx(null);
    }
  };

  const download = async (kind: "docx" | "pptx") => {
    if (sections.length === 0) return;
    try {
      const fn = kind === "docx" ? downloadGeneratedDocx : downloadGeneratedPptx;
      await fn(title || "문서", sections);
    } catch {
      message.error(`${kind} 다운로드 실패`);
    }
  };

  const handleReview = async () => {
    if (sections.length === 0) return;
    setReviewing(true);
    try {
      const res = await reviewDocument({
        topic: topic.trim(),
        doc_type: docType,
        title: title || "문서",
        sections,
        use_nas: useNas,
      });
      setReview(res);
      message.success(`품질 검증 완료 — 점수 ${res.overall_score}/100 ($${res.cost_usd.toFixed(4)})`);
    } catch {
      message.error("품질 검증 실패");
    } finally {
      setReviewing(false);
    }
  };

  return (
    <div style={{ maxWidth: 1080 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
          문서 생성{" "}
          <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
            요구 기반 · RAG 초안 · 편집/재생성
          </Text>
        </h2>
        <Text type="secondary">
          주제를 입력하면 회사 NAS 자료를 참고해 초안을 만들고, 섹션을 직접 고치거나 다시 생성할 수 있습니다.
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
          title={
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              variant="borderless"
              style={{ fontSize: 16, fontWeight: 600, padding: 0 }}
            />
          }
          extra={
            <Space>
              <Button icon={<AuditOutlined />} loading={reviewing} onClick={handleReview}>
                품질 검증
              </Button>
              <Button icon={<DownloadOutlined />} onClick={() => download("docx")}>
                .docx
              </Button>
              <Button icon={<DownloadOutlined />} onClick={() => download("pptx")}>
                PPT
              </Button>
            </Space>
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

          {review && (
            <Alert
              type={review.overall_score >= 70 ? "success" : review.overall_score >= 40 ? "warning" : "error"}
              style={{ marginBottom: 16 }}
              showIcon
              message={`품질 점수 ${review.overall_score}/100`}
              description={
                <div>
                  <div style={{ marginBottom: 8 }}>{review.summary}</div>
                  {review.section_reviews.some((r) => !r.grounded || r.issues.length > 0) && (
                    <List
                      size="small"
                      dataSource={review.section_reviews.filter((r) => !r.grounded || r.issues.length > 0)}
                      renderItem={(r) => (
                        <List.Item style={{ display: "block", paddingLeft: 0 }}>
                          <Text strong>{r.heading}</Text>{" "}
                          {!r.grounded && <Tag color="red">근거 불충분</Tag>}
                          {r.issues.map((iss, k) => (
                            <div key={k} style={{ fontSize: 12, color: "#cf1322" }}>· {iss}</div>
                          ))}
                          {r.suggestions.map((sg, k) => (
                            <div key={k} style={{ fontSize: 12, color: "#8c8c8c" }}>→ {sg}</div>
                          ))}
                        </List.Item>
                      )}
                    />
                  )}
                  {review.missing.length > 0 && (
                    <div style={{ marginTop: 8 }}>
                      <Text type="secondary" style={{ fontSize: 12 }}>누락/보강: </Text>
                      {review.missing.map((m, k) => (
                        <Tag key={k} color="orange" style={{ marginBottom: 4 }}>{m.slice(0, 40)}</Tag>
                      ))}
                    </div>
                  )}
                </div>
              }
            />
          )}

          <Space direction="vertical" style={{ width: "100%" }} size={16}>
            {sections.map((s, i) => (
              <div key={i} style={{ borderTop: i > 0 ? "1px solid #f0f0f0" : "none", paddingTop: i > 0 ? 12 : 0 }}>
                <Space.Compact style={{ width: "100%", marginBottom: 6 }}>
                  <Input
                    value={s.heading}
                    onChange={(e) => updateSection(i, { heading: e.target.value })}
                    style={{ fontWeight: 600 }}
                  />
                  <Popconfirm title="이 섹션을 삭제할까요?" onConfirm={() => deleteSection(i)}>
                    <Button icon={<DeleteOutlined />} danger />
                  </Popconfirm>
                </Space.Compact>
                <Input.TextArea
                  value={s.body}
                  onChange={(e) => updateSection(i, { body: e.target.value })}
                  autoSize={{ minRows: 3, maxRows: 16 }}
                  style={{ marginBottom: 6 }}
                />
                <Space.Compact style={{ width: "100%" }}>
                  <Input
                    placeholder="수정 요청(선택) — 예: 견적 표를 더 구체적으로"
                    value={feedbacks[i] ?? ""}
                    onChange={(e) => setFeedbacks((prev) => ({ ...prev, [i]: e.target.value }))}
                    onPressEnter={() => handleRegenerate(i)}
                    size="small"
                  />
                  <Button
                    size="small"
                    icon={<ReloadOutlined />}
                    loading={regenIdx === i}
                    onClick={() => handleRegenerate(i)}
                  >
                    재생성
                  </Button>
                </Space.Compact>
              </div>
            ))}
          </Space>

          <Button
            type="dashed"
            icon={<PlusOutlined />}
            onClick={addSection}
            style={{ marginTop: 16 }}
            block
          >
            섹션 추가
          </Button>
        </Card>
      )}
    </div>
  );
}
