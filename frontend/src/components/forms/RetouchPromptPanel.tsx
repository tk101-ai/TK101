import { useCallback, useEffect, useState } from "react";
import {
  Avatar,
  Button,
  Drawer,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Segmented,
  Space,
  Switch,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  CopyOutlined,
  DeleteOutlined,
  FolderOpenOutlined,
  FundProjectionScreenOutlined,
  SaveOutlined,
  ShareAltOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  deleteRetouchPreset,
  generateHtmlDeck,
  generateRetouchPrompt,
  listRetouchPresets,
  listSharedRetouchPresets,
  saveRetouchPreset,
  updateRetouchPreset,
  type DocSection,
  type DocType,
  type RetouchPreset,
  type RetouchTarget,
  type SharedRetouchPreset,
} from "../../api/docgen";
import { triggerBlobDownload } from "../../utils/download";

const { Text, Paragraph } = Typography;

const TARGET_OPTIONS: { label: string; value: RetouchTarget }[] = [
  { label: "범용", value: "general" },
  { label: "Gamma", value: "gamma" },
  { label: "GPT", value: "gpt" },
  { label: "Gemini", value: "gemini" },
  { label: "사내 생성기용", value: "internal" },
];

interface RetouchPromptPanelProps {
  title: string;
  sections: DocSection[];
  docType: DocType;
  topic?: string | null;
  sourceDocumentId?: string | null;
  /** 리터치 프롬프트를 디자인 지시문으로 먹여 문서를 다시 생성(내부 재생성). */
  onRegenerate?: (directive: string) => Promise<void>;
  /** 재생성 진행 중(상위 생성 상태). */
  regenerating?: boolean;
}

export default function RetouchPromptPanel({
  title,
  sections,
  docType,
  topic,
  sourceDocumentId,
  onRegenerate,
  regenerating,
}: RetouchPromptPanelProps) {
  const [target, setTarget] = useState<RetouchTarget>("general");
  const [generating, setGenerating] = useState(false);
  const [promptText, setPromptText] = useState("");

  const [saveOpen, setSaveOpen] = useState(false);
  const [presetTitle, setPresetTitle] = useState("");
  const [saving, setSaving] = useState(false);

  const [drawerOpen, setDrawerOpen] = useState(false);

  const handleGenerate = async () => {
    if (sections.length === 0) {
      message.warning("먼저 문서를 생성하세요");
      return;
    }
    setGenerating(true);
    try {
      const res = await generateRetouchPrompt({
        title,
        sections,
        doc_type: docType,
        topic,
        target,
        source_document_id: sourceDocumentId ?? null,
      });
      setPromptText(res.prompt_text);
      message.success("리터치 프롬프트를 생성했습니다");
    } catch (e) {
      message.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "프롬프트 생성에 실패했습니다",
      );
    } finally {
      setGenerating(false);
    }
  };

  const [deckBusy, setDeckBusy] = useState(false);
  const handleHtmlDeck = async () => {
    if (sections.length === 0) {
      message.warning("먼저 문서를 생성하세요");
      return;
    }
    if (!promptText.trim()) {
      message.warning("디자인 프롬프트가 필요합니다");
      return;
    }
    setDeckBusy(true);
    try {
      const res = await generateHtmlDeck({
        title: title || "문서",
        sections,
        doc_type: docType,
        design_prompt: promptText,
      });
      const blob = new Blob([res.html], { type: "text/html" });
      // 새 탭에서 디자인 덱 미리보기(브라우저 인쇄→PDF 가능).
      window.open(URL.createObjectURL(blob), "_blank");
      triggerBlobDownload(blob, `${title || "deck"}.html`);
      message.success(
        `HTML 디자인 덱 생성 — 새 탭에서 열림 · 인쇄→PDF 가능 (비용 $${res.cost_usd.toFixed(3)})`,
      );
    } catch (e) {
      message.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "HTML 덱 생성에 실패했습니다",
      );
    } finally {
      setDeckBusy(false);
    }
  };

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(promptText);
      message.success("복사했습니다 — 다른 AI에 붙여넣어 재디자인하세요");
    } catch {
      message.error("복사에 실패했습니다");
    }
  };

  const openSave = () => {
    setPresetTitle(title ? `${title} — 리터치` : "리터치 프롬프트");
    setSaveOpen(true);
  };

  const handleSave = async () => {
    if (!presetTitle.trim()) {
      message.warning("프리셋 이름을 입력하세요");
      return;
    }
    setSaving(true);
    try {
      await saveRetouchPreset({
        title: presetTitle.trim(),
        prompt_text: promptText,
        doc_type: docType,
        target,
        source_document_id: sourceDocumentId ?? null,
      });
      message.success("프리셋으로 저장했습니다");
      setSaveOpen(false);
    } catch {
      message.error("저장에 실패했습니다");
    } finally {
      setSaving(false);
    }
  };

  const applyPreset = (preset: RetouchPreset | SharedRetouchPreset) => {
    setPromptText(preset.prompt_text);
    setTarget(preset.target);
    setDrawerOpen(false);
    message.success(`'${preset.title}' 프리셋을 불러왔습니다`);
  };

  return (
    <div
      style={{
        marginTop: 20,
        paddingTop: 16,
        borderTop: "1px solid rgba(0,0,0,0.08)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 8,
        }}
      >
        <Space>
          <ThunderboltOutlined style={{ color: "#2D7FF9" }} />
          <Text strong>리터치 프롬프트</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            다른 AI로 재디자인·재생성할 브리프를 만듭니다
          </Text>
        </Space>
        <Button size="small" icon={<FolderOpenOutlined />} onClick={() => setDrawerOpen(true)}>
          프리셋 불러오기
        </Button>
      </div>

      <Space wrap style={{ marginBottom: 12 }}>
        <Segmented
          options={TARGET_OPTIONS}
          value={target}
          onChange={(v) => setTarget(v as RetouchTarget)}
        />
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          loading={generating}
          onClick={handleGenerate}
        >
          프롬프트 생성
        </Button>
      </Space>

      {promptText && (
        <div>
          <Input.TextArea
            value={promptText}
            onChange={(e) => setPromptText(e.target.value)}
            autoSize={{ minRows: 10, maxRows: 24 }}
            style={{ fontFamily: "monospace", fontSize: 12.5 }}
          />
          <Space style={{ marginTop: 10 }} wrap>
            <Tooltip title="이 디자인 프롬프트를 그대로 적용한 HTML 슬라이드 덱을 만들어 새 탭에서 엽니다 (브라우저 인쇄→PDF). 색·폰트·레이아웃이 실제로 반영됩니다.">
              <Button
                type="primary"
                icon={<FundProjectionScreenOutlined />}
                loading={deckBusy}
                onClick={handleHtmlDeck}
              >
                HTML 디자인 덱 생성
              </Button>
            </Tooltip>
            <Button icon={<CopyOutlined />} onClick={handleCopy}>
              복사
            </Button>
            <Button icon={<SaveOutlined />} onClick={openSave}>
              프리셋으로 저장
            </Button>
            {onRegenerate && (
              <Tooltip title="이 프롬프트를 디자인 지시문으로 우리 생성기에 먹여 문서를 다시 생성합니다">
                <Button
                  icon={<SyncOutlined />}
                  loading={regenerating}
                  onClick={() => onRegenerate(promptText)}
                >
                  이 프롬프트로 다시 생성
                </Button>
              </Tooltip>
            )}
          </Space>
        </div>
      )}

      <Modal
        open={saveOpen}
        title="프리셋으로 저장"
        okText="저장"
        cancelText="취소"
        confirmLoading={saving}
        onOk={handleSave}
        onCancel={() => setSaveOpen(false)}
      >
        <Text type="secondary" style={{ fontSize: 12 }}>
          저장 후 보관함에서 재사용하거나 공유할 수 있습니다.
        </Text>
        <Input
          style={{ marginTop: 10 }}
          value={presetTitle}
          onChange={(e) => setPresetTitle(e.target.value)}
          placeholder="프리셋 이름"
          maxLength={300}
        />
      </Modal>

      <PresetDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} onApply={applyPreset} />
    </div>
  );
}

// ── 프리셋 불러오기 드로어 (내 프리셋 / 공유 프리셋) ──

function PresetDrawer({
  open,
  onClose,
  onApply,
}: {
  open: boolean;
  onClose: () => void;
  onApply: (preset: RetouchPreset | SharedRetouchPreset) => void;
}) {
  const [tab, setTab] = useState<"mine" | "shared">("mine");
  const [query, setQuery] = useState("");
  const [mine, setMine] = useState<RetouchPreset[]>([]);
  const [shared, setShared] = useState<SharedRetouchPreset[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "mine") setMine(await listRetouchPresets(query || undefined));
      else setShared(await listSharedRetouchPresets(query || undefined));
    } catch {
      message.error("프리셋을 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [tab, query]);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const handleToggleShare = async (id: string, next: boolean) => {
    setMine((prev) => prev.map((p) => (p.id === id ? { ...p, is_shared: next } : p)));
    try {
      await updateRetouchPreset(id, { is_shared: next });
      message.success(next ? "공유했습니다" : "공유를 해제했습니다");
    } catch {
      setMine((prev) => prev.map((p) => (p.id === id ? { ...p, is_shared: !next } : p)));
      message.error("공유 설정에 실패했습니다");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteRetouchPreset(id);
      setMine((prev) => prev.filter((p) => p.id !== id));
      message.success("삭제했습니다");
    } catch {
      message.error("삭제에 실패했습니다");
    }
  };

  const previewOf = (text: string) => (text.length > 140 ? `${text.slice(0, 140)}…` : text);

  return (
    <Drawer title="리터치 프롬프트 프리셋" open={open} onClose={onClose} width={520}>
      <Input.Search
        allowClear
        placeholder="제목으로 검색"
        style={{ marginBottom: 12 }}
        onSearch={(v) => setQuery(v.trim())}
      />
      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as "mine" | "shared")}
        items={[
          {
            key: "mine",
            label: "내 프리셋",
            children: (
              <List
                loading={loading && tab === "mine"}
                dataSource={mine}
                locale={{
                  emptyText: <Empty description="저장한 프리셋이 없습니다" />,
                }}
                renderItem={(p) => (
                  <List.Item
                    actions={[
                      <Tooltip key="share" title="공유 갤러리에 공개">
                        <Space size={4}>
                          <ShareAltOutlined style={{ color: "rgba(0,0,0,0.45)" }} />
                          <Switch
                            size="small"
                            checked={p.is_shared}
                            onChange={(v) => handleToggleShare(p.id, v)}
                          />
                        </Space>
                      </Tooltip>,
                      <Button key="apply" type="link" size="small" onClick={() => onApply(p)}>
                        불러오기
                      </Button>,
                      <Popconfirm
                        key="del"
                        title="삭제할까요?"
                        okText="삭제"
                        okButtonProps={{ danger: true }}
                        cancelText="취소"
                        onConfirm={() => handleDelete(p.id)}
                      >
                        <Button type="text" size="small" danger icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text strong>{p.title}</Text>
                          <Tag bordered={false}>{p.target}</Tag>
                          {p.doc_type && (
                            <Tag bordered={false} color="geekblue">
                              {p.doc_type}
                            </Tag>
                          )}
                        </Space>
                      }
                      description={
                        <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                          {previewOf(p.prompt_text)}
                        </Paragraph>
                      }
                    />
                  </List.Item>
                )}
              />
            ),
          },
          {
            key: "shared",
            label: "공유 프리셋",
            children: (
              <List
                loading={loading && tab === "shared"}
                dataSource={shared}
                locale={{
                  emptyText: <Empty description="공유된 프리셋이 없습니다" />,
                }}
                renderItem={(p) => (
                  <List.Item
                    actions={[
                      <Button key="apply" type="link" size="small" onClick={() => onApply(p)}>
                        불러오기
                      </Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space>
                          <Text strong>{p.title}</Text>
                          <Tag bordered={false}>{p.target}</Tag>
                          {p.is_mine && (
                            <Tag bordered={false} color="green">
                              내 프리셋
                            </Tag>
                          )}
                        </Space>
                      }
                      description={
                        <Space direction="vertical" size={2}>
                          <Space size={6}>
                            <Avatar size={18} icon={<UserOutlined />} />
                            <Text style={{ fontSize: 12 }}>{p.owner_name ?? "알 수 없음"}</Text>
                            {p.owner_department && (
                              <Tag bordered={false} style={{ fontSize: 11 }}>
                                {p.owner_department}
                              </Tag>
                            )}
                          </Space>
                          <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                            {previewOf(p.prompt_text)}
                          </Paragraph>
                        </Space>
                      }
                    />
                  </List.Item>
                )}
              />
            ),
          },
        ]}
      />
    </Drawer>
  );
}
