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
  Tag,
  Typography,
  Upload,
} from "antd";
import type { UploadFile } from "antd";
import {
  AuditOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  UploadOutlined,
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
  type DocSectionReview,
  type DocType,
  type SourceMode,
} from "../../api/docgen";

const { Text } = Typography;
const DOC_TYPES: DocType[] = ["제안서", "계획서", "보고서", "일반"];
const SOURCE_OPTIONS: { label: string; value: SourceMode }[] = [
  { label: "NAS 자료(RAG)", value: "rag" },
  { label: "업로드 문서", value: "uploaded" },
  { label: "둘 다", value: "both" },
];
const UPLOAD_ACCEPT = ".pdf,.docx,.xlsx,.csv,.txt,.pptx";
const MAX_UPLOAD_FILES = 5;

/**
 * 요구 기반 문서 생성 (T5 확장).
 * 주제 → NAS RAG → Claude 초안 → 인라인 편집/섹션 재생성 → docx/PPT 다운로드.
 */
export default function DocGenPage() {
  const [topic, setTopic] = useState("");
  const [docType, setDocType] = useState<DocType>("제안서");
  const [sourceMode, setSourceMode] = useState<SourceMode>("rag");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DocGenResponse | null>(null);

  // 업로드된 실제 File 객체들 — 생성·재생성·검수 핸들러가 공유한다(무상태 멀티파트 재전송).
  const files = fileList
    .map((f) => f.originFileObj as File | undefined)
    .filter((f): f is File => !!f);
  const showUpload = sourceMode !== "rag";

  // 생성 결과를 편집 가능한 상태로 보관(다운로드·재생성은 이 상태 기준).
  const [title, setTitle] = useState("");
  const [sections, setSections] = useState<DocSection[]>([]);
  const [feedbacks, setFeedbacks] = useState<Record<number, string>>({});
  const [regenIdx, setRegenIdx] = useState<number | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [review, setReview] = useState<DocReviewResponse | null>(null);
  // 검수 이슈 기반 자동 보강(원클릭) 진행 상태.
  const [autoFixHeading, setAutoFixHeading] = useState<string | null>(null);
  const [autoFixingAll, setAutoFixingAll] = useState(false);

  const handleGenerate = async () => {
    const t = topic.trim();
    if (t.length < 2) {
      message.warning("작성 요구/주제를 입력하세요");
      return;
    }
    if (sourceMode === "uploaded" && files.length === 0) {
      message.warning("업로드 문서를 1개 이상 추가하거나 출처를 바꾸세요");
      return;
    }
    setBusy(true);
    try {
      const res = await generateDocument({
        topic: t,
        doc_type: docType,
        source_mode: sourceMode,
        files,
      });
      setResult(res);
      setTitle(res.title);
      setSections(res.sections);
      setFeedbacks({});
      setReview(null);
      message.success(`초안 생성 완료 (참고 ${res.sources.length}건)`);
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
        source_mode: sourceMode,
        files,
      });
      updateSection(i, res.section);
      setFeedbacks((prev) => ({ ...prev, [i]: "" }));
      message.success("섹션 재생성 완료");
    } catch {
      message.error("섹션 재생성 실패");
    } finally {
      setRegenIdx(null);
    }
  };

  // 검수 결과의 issues + suggestions 를 재생성용 feedback 문자열로 합친다.
  const buildReviewFeedback = (r: DocSectionReview): string => {
    const lines = [
      ...(r.grounded ? [] : ["근거가 불충분합니다. 참고 자료에 기반해 사실을 보강하세요."]),
      ...r.issues.map((iss) => `문제: ${iss}`),
      ...r.suggestions.map((sg) => `개선: ${sg}`),
    ];
    return lines.join("\n");
  };

  // 검수 항목 heading 을 현재 섹션 배열의 인덱스로 매핑(편집으로 못 찾으면 -1).
  const findSectionIndex = (heading: string): number =>
    sections.findIndex((s) => s.heading.trim() === heading.trim());

  // 한 섹션을 검수 피드백 기준으로 재생성하고, 해당 섹션의 검수 표시는 제거(재검증 필요).
  const regenerateFromReview = async (r: DocSectionReview): Promise<boolean> => {
    const idx = findSectionIndex(r.heading);
    if (idx < 0) {
      message.warning(`"${r.heading}" 섹션을 찾지 못했습니다(제목이 바뀐 듯). 건너뜁니다.`);
      return false;
    }
    const res = await regenerateSection({
      topic: topic.trim(),
      doc_type: docType,
      heading: sections[idx].heading,
      current_body: sections[idx].body,
      feedback: buildReviewFeedback(r),
      source_mode: sourceMode,
      files,
    });
    updateSection(idx, res.section);
    // 재생성된 섹션의 검수 결과는 더 이상 유효하지 않으므로 목록에서 제거.
    setReview((prev) =>
      prev
        ? { ...prev, section_reviews: prev.section_reviews.filter((sr) => sr !== r) }
        : prev,
    );
    return true;
  };

  // 단일 섹션 "이 이슈 반영해 재생성".
  const handleAutoFixSection = async (r: DocSectionReview) => {
    setAutoFixHeading(r.heading);
    try {
      const ok = await regenerateFromReview(r);
      if (ok) message.success(`"${r.heading}" 이슈 반영 재생성 완료`);
    } catch {
      message.error("이슈 반영 재생성 실패");
    } finally {
      setAutoFixHeading(null);
    }
  };

  // "지적된 섹션 모두 자동 보강" — 이슈 있는 섹션들을 순차 재생성.
  const handleAutoFixAll = async () => {
    if (!review) return;
    const targets = review.section_reviews.filter((r) => !r.grounded || r.issues.length > 0);
    if (targets.length === 0) return;
    setAutoFixingAll(true);
    let done = 0;
    let skipped = 0;
    try {
      for (const r of targets) {
        try {
          const ok = await regenerateFromReview(r);
          if (ok) done += 1;
          else skipped += 1;
        } catch {
          skipped += 1;
        }
      }
      message.success(
        `자동 보강 완료 — ${done}개 재생성${skipped > 0 ? `, ${skipped}개 건너뜀` : ""}`,
      );
    } finally {
      setAutoFixingAll(false);
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
        source_mode: sourceMode,
        files,
      });
      setReview(res);
      message.success(`품질 검증 완료 — 점수 ${res.overall_score}/100`);
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
          <Space wrap size={[12, 8]}>
            <Segmented
              options={DOC_TYPES}
              value={docType}
              onChange={(v) => setDocType(v as DocType)}
            />
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>출처</Text>
              <Segmented
                size="small"
                options={SOURCE_OPTIONS}
                value={sourceMode}
                onChange={(v) => setSourceMode(v as SourceMode)}
              />
            </Space>
          </Space>
          {showUpload && (
            <Upload
              multiple
              accept={UPLOAD_ACCEPT}
              fileList={fileList}
              maxCount={MAX_UPLOAD_FILES}
              beforeUpload={() => false}
              onChange={({ fileList: fl }) => setFileList(fl.slice(0, MAX_UPLOAD_FILES))}
            >
              <Button icon={<UploadOutlined />} size="small">
                참고 문서 업로드 (최대 {MAX_UPLOAD_FILES}개 · PDF/DOCX/XLSX/CSV/TXT/PPTX)
              </Button>
            </Upload>
          )}
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
                    <>
                      <Button
                        size="small"
                        type="primary"
                        ghost
                        icon={<SyncOutlined />}
                        loading={autoFixingAll}
                        disabled={autoFixHeading !== null}
                        onClick={handleAutoFixAll}
                        style={{ marginBottom: 8 }}
                      >
                        지적된 섹션 모두 자동 보강
                      </Button>
                      <List
                        size="small"
                        dataSource={review.section_reviews.filter((r) => !r.grounded || r.issues.length > 0)}
                        renderItem={(r) => (
                          <List.Item style={{ display: "block", paddingLeft: 0 }}>
                            <Space align="center" wrap style={{ marginBottom: 2 }}>
                              <Text strong>{r.heading}</Text>
                              {!r.grounded && <Tag color="red">근거 불충분</Tag>}
                              {findSectionIndex(r.heading) < 0 && <Tag>섹션 없음</Tag>}
                              <Button
                                size="small"
                                icon={<SyncOutlined />}
                                loading={autoFixHeading === r.heading}
                                disabled={
                                  autoFixingAll ||
                                  (autoFixHeading !== null && autoFixHeading !== r.heading) ||
                                  findSectionIndex(r.heading) < 0
                                }
                                onClick={() => handleAutoFixSection(r)}
                              >
                                이 이슈 반영해 재생성
                              </Button>
                            </Space>
                            {r.issues.map((iss, k) => (
                              <div key={k} style={{ fontSize: 12, color: "#cf1322" }}>· {iss}</div>
                            ))}
                            {r.suggestions.map((sg, k) => (
                              <div key={k} style={{ fontSize: 12, color: "#8c8c8c" }}>→ {sg}</div>
                            ))}
                          </List.Item>
                        )}
                      />
                    </>
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
