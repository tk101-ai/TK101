import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Button,
  Empty,
  Input,
  Modal,
  Radio,
  Segmented,
  Select,
  Space,
  Spin,
  Steps,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import type { UploadFile } from "antd";
import { FileTextOutlined, RobotOutlined, UploadOutlined } from "@ant-design/icons";
import {
  listRetouchPresets,
  listSharedRetouchPresets,
  type DocType,
  type RetouchPreset,
  type SharedRetouchPreset,
  type SourceMode,
} from "../../api/docgen";
import { createFormJob, listFormTemplates, type FormTemplateListItem } from "../../api/forms";

const { Text, Paragraph } = Typography;

/** 톤앤매너 프리셋 — directive 스니펫으로 생성 프롬프트에 주입. */
export const TONE_PRESETS: { key: string; label: string; directive: string }[] = [
  {
    key: "formal",
    label: "격식·공식",
    directive: "격식 있고 공식적인 비즈니스 문어체. 정중하고 신뢰감 있는 톤으로 작성한다.",
  },
  {
    key: "standard",
    label: "표준 비즈니스",
    directive: "표준적인 비즈니스 톤. 명료하고 간결하게 작성한다.",
  },
  {
    key: "casual",
    label: "친근·캐주얼",
    directive: "친근하고 부드러운 톤. 쉽게 읽히되 전문성은 유지한다.",
  },
  {
    key: "impactful",
    label: "임팩트·설득",
    directive:
      "강한 설득력과 임팩트. 핵심 메시지를 앞세우고 수치·근거로 밀어붙이는 톤으로 작성한다.",
  },
];

export function toneDirective(key?: string): string | undefined {
  return TONE_PRESETS.find((t) => t.key === key)?.directive;
}

export interface WizardFreePayload {
  docType: DocType;
  preferredFormat: "docx" | "pptx";
  tone?: string;
  designPresetId?: string;
  sourceMode: SourceMode;
  fileList: UploadFile[];
  highQuality: boolean;
  topic: string;
}

interface DocCreateWizardProps {
  open: boolean;
  onClose: () => void;
  /** 자유 작성 — DocGenPage 가 실제 생성·결과 표시를 담당. */
  onFreeGenerate: (payload: WizardFreePayload) => void;
}

const DOC_TYPES: DocType[] = ["제안서", "계획서", "보고서", "일반"];
const SOURCE_OPTIONS: { label: string; value: SourceMode }[] = [
  { label: "NAS 자료(RAG)", value: "rag" },
  { label: "업로드 문서", value: "uploaded" },
  { label: "둘 다", value: "both" },
];
const UPLOAD_ACCEPT = ".pdf,.docx,.xlsx,.csv,.txt,.pptx";
const MAX_UPLOAD_FILES = 5;

export default function DocCreateWizard({ open, onClose, onFreeGenerate }: DocCreateWizardProps) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"free" | "form" | undefined>();
  const [step, setStep] = useState(0);

  // 자유 작성 수집값.
  const [docType, setDocType] = useState<DocType>("제안서");
  const [preferredFormat, setPreferredFormat] = useState<"docx" | "pptx">("pptx");
  const [tone, setTone] = useState<string | undefined>("standard");
  const [designPresetId, setDesignPresetId] = useState<string | undefined>();
  const [sourceMode, setSourceMode] = useState<SourceMode>("rag");
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [highQuality, setHighQuality] = useState(false);
  const [topic, setTopic] = useState("");

  // 디자인 프리셋 목록.
  const [myPresets, setMyPresets] = useState<RetouchPreset[]>([]);
  const [sharedPresets, setSharedPresets] = useState<SharedRetouchPreset[]>([]);

  // 양식 분기.
  const [templates, setTemplates] = useState<FormTemplateListItem[]>([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>();
  const [creatingJob, setCreatingJob] = useState(false);

  // 모달 열릴 때 리셋 + 디자인 프리셋 로드.
  useEffect(() => {
    if (!open) return;
    setMode(undefined);
    setStep(0);
    setSelectedTemplateId(undefined);
    void (async () => {
      try {
        const [mine, shared] = await Promise.all([
          listRetouchPresets(),
          listSharedRetouchPresets(),
        ]);
        setMyPresets(mine);
        setSharedPresets(shared);
      } catch {
        // 프리셋 없어도 진행 가능.
      }
    })();
  }, [open]);

  // 양식 단계 진입 시 템플릿 로드.
  useEffect(() => {
    if (open && mode === "form" && step === 1 && templates.length === 0) {
      setTemplatesLoading(true);
      void listFormTemplates()
        .then(setTemplates)
        .catch(() => message.error("양식 목록을 불러오지 못했습니다"))
        .finally(() => setTemplatesLoading(false));
    }
  }, [open, mode, step, templates.length]);

  const presetOptions = useMemo(
    () => [
      {
        label: "내 프리셋",
        options: myPresets.map((p) => ({
          label: `${p.title} · ${p.target}`,
          value: p.id,
        })),
      },
      {
        label: "공유 프리셋",
        options: sharedPresets
          .filter((p) => !p.is_mine)
          .map((p) => ({
            label: `${p.title} · ${p.owner_name ?? "?"}`,
            value: p.id,
          })),
      },
    ],
    [myPresets, sharedPresets],
  );

  const freeSteps = ["방식", "종류·포맷", "톤·디자인", "자료·품질", "내용"];
  const formSteps = ["방식", "양식 선택"];
  const stepsItems = (mode === "form" ? formSteps : freeSteps).map((t) => ({
    title: t,
  }));
  const lastStep = mode === "form" ? 1 : 4;

  const next = () => setStep((s) => s + 1);
  const prev = () => setStep((s) => Math.max(0, s - 1));

  const handleFreeFinish = () => {
    if (topic.trim().length < 2) {
      message.warning("원하는 내용·데이터를 입력하세요");
      return;
    }
    if (sourceMode === "uploaded" && fileList.length === 0) {
      message.warning("업로드 문서를 추가하거나 출처를 바꾸세요");
      return;
    }
    onFreeGenerate({
      docType,
      preferredFormat,
      tone,
      designPresetId,
      sourceMode,
      fileList,
      highQuality,
      topic: topic.trim(),
    });
    onClose();
  };

  const handleFormFinish = async () => {
    if (!selectedTemplateId) {
      message.warning("양식을 선택하세요");
      return;
    }
    setCreatingJob(true);
    try {
      const job = await createFormJob(selectedTemplateId);
      onClose();
      navigate(`/forms/jobs/${job.id}/sources`);
    } catch {
      message.error("양식 작업 시작에 실패했습니다");
    } finally {
      setCreatingJob(false);
    }
  };

  const showUpload = sourceMode !== "rag";

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title="문서 만들기"
      width={680}
      destroyOnClose
      footer={null}
    >
      <Steps size="small" current={step} items={stepsItems} style={{ marginBottom: 20 }} />

      {/* ── 0. 방식 선택 ── */}
      {step === 0 && (
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Text type="secondary">어떻게 만들까요?</Text>
          <Radio.Group
            value={mode}
            onChange={(e) => setMode(e.target.value)}
            style={{ width: "100%" }}
          >
            <Space direction="vertical" style={{ width: "100%" }}>
              <Radio value="free">
                <Space>
                  <RobotOutlined />
                  <span>
                    <b>자유 작성</b> — 주제·자료를 주면 AI가 새로 작성(Word/PPT)
                  </span>
                </Space>
              </Radio>
              <Radio value="form">
                <Space>
                  <FileTextOutlined />
                  <span>
                    <b>기존 양식 사용</b> — 회사 양식(.docx/.xlsx)에 내용 채우기
                  </span>
                </Space>
              </Radio>
            </Space>
          </Radio.Group>
        </Space>
      )}

      {/* ── 양식: 1. 양식 선택 ── */}
      {mode === "form" && step === 1 && (
        <div>
          {templatesLoading ? (
            <div style={{ textAlign: "center", padding: 40 }}>
              <Spin />
            </div>
          ) : templates.length === 0 ? (
            <Empty description="등록된 양식이 없습니다. 양식 라이브러리에서 먼저 업로드하세요." />
          ) : (
            <Radio.Group
              value={selectedTemplateId}
              onChange={(e) => setSelectedTemplateId(e.target.value)}
              style={{ width: "100%" }}
            >
              <Space direction="vertical" style={{ width: "100%" }}>
                {templates.map((t) => (
                  <Radio key={t.id} value={t.id}>
                    <Space>
                      <span>{t.name}</span>
                      {t.file_format && <Tag bordered={false}>{t.file_format}</Tag>}
                    </Space>
                  </Radio>
                ))}
              </Space>
            </Radio.Group>
          )}
        </div>
      )}

      {/* ── 자유: 1. 종류·포맷 ── */}
      {mode === "free" && step === 1 && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              문서 종류
            </Text>
            <div style={{ marginTop: 6 }}>
              <Segmented
                options={DOC_TYPES}
                value={docType}
                onChange={(v) => setDocType(v as DocType)}
              />
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              출력 포맷
            </Text>
            <div style={{ marginTop: 6 }}>
              <Segmented
                options={[
                  { label: "PPT", value: "pptx" },
                  { label: "Word", value: "docx" },
                ]}
                value={preferredFormat}
                onChange={(v) => setPreferredFormat(v as "docx" | "pptx")}
              />
              <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6 }}>
                Excel은 「기존 양식 사용」에서 .xlsx 양식으로 만들 수 있어요.
              </Paragraph>
            </div>
          </div>
        </Space>
      )}

      {/* ── 자유: 2. 톤·디자인 ── */}
      {mode === "free" && step === 2 && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              톤앤매너
            </Text>
            <div style={{ marginTop: 6 }}>
              <Segmented
                options={TONE_PRESETS.map((t) => ({ label: t.label, value: t.key }))}
                value={tone}
                onChange={(v) => setTone(v as string)}
              />
            </div>
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              디자인 프리셋 (선택)
            </Text>
            <div style={{ marginTop: 6 }}>
              <Select
                style={{ minWidth: 240 }}
                placeholder="없음"
                allowClear
                value={designPresetId}
                onChange={(v) => setDesignPresetId(v)}
                options={presetOptions}
              />
              <Paragraph type="secondary" style={{ fontSize: 12, marginTop: 6 }}>
                저장·공유된 리터치 프리셋의 디자인 방향을 첫 생성부터 적용합니다.
              </Paragraph>
            </div>
          </div>
        </Space>
      )}

      {/* ── 자유: 3. 자료·품질 ── */}
      {mode === "free" && step === 3 && (
        <Space direction="vertical" size={16} style={{ width: "100%" }}>
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              참고 자료
            </Text>
            <div style={{ marginTop: 6 }}>
              <Segmented
                options={SOURCE_OPTIONS}
                value={sourceMode}
                onChange={(v) => setSourceMode(v as SourceMode)}
              />
            </div>
          </div>
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
                참고 문서 업로드 (최대 {MAX_UPLOAD_FILES}개)
              </Button>
            </Upload>
          )}
          <div>
            <Text type="secondary" style={{ fontSize: 12 }}>
              품질
            </Text>
            <div style={{ marginTop: 6 }}>
              <Segmented
                options={[
                  { label: "초안(빠름)", value: "draft" },
                  { label: "고품질(검수)", value: "high" },
                ]}
                value={highQuality ? "high" : "draft"}
                onChange={(v) => setHighQuality(v === "high")}
              />
            </div>
          </div>
        </Space>
      )}

      {/* ── 자유: 4. 내용 ── */}
      {mode === "free" && step === 4 && (
        <Space direction="vertical" size={8} style={{ width: "100%" }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            원하는 내용·데이터를 자세히 적을수록 결과가 좋아집니다.
          </Text>
          <Input.TextArea
            rows={6}
            placeholder="예: 신세계백화점 대상 중국 SNS 운영 대행 제안서. 운영 채널(샤오훙슈·더우인), 월 예산 1,500만원, 6개월 일정, 기대 KPI 포함."
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
          />
        </Space>
      )}

      {/* ── 푸터 ── */}
      <div
        style={{
          marginTop: 24,
          display: "flex",
          justifyContent: "space-between",
        }}
      >
        <Button onClick={onClose}>취소</Button>
        <Space>
          {step > 0 && <Button onClick={prev}>이전</Button>}
          {step < lastStep && (
            <Button type="primary" disabled={step === 0 && !mode} onClick={next}>
              다음
            </Button>
          )}
          {mode === "free" && step === lastStep && (
            <Button type="primary" onClick={handleFreeFinish}>
              생성
            </Button>
          )}
          {mode === "form" && step === lastStep && (
            <Button type="primary" loading={creatingJob} onClick={handleFormFinish}>
              양식 작성 시작
            </Button>
          )}
        </Space>
      </div>
    </Modal>
  );
}
