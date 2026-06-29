import { useCallback, useEffect, useState } from "react";
import {
  Avatar,
  Button,
  ColorPicker,
  Divider,
  Empty,
  Input,
  List,
  Modal,
  Popconfirm,
  Select,
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
  EditOutlined,
  PlusOutlined,
  ShareAltOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  deleteRetouchPreset,
  listRetouchPresets,
  listSharedRetouchPresets,
  saveRetouchPreset,
  updateRetouchPreset,
  type DocType,
  type RetouchPreset,
  type RetouchTarget,
  type SharedRetouchPreset,
} from "../../api/docgen";

const { Text, Paragraph } = Typography;

const TARGET_OPTIONS: { label: string; value: RetouchTarget }[] = [
  { label: "범용", value: "general" },
  { label: "Gamma", value: "gamma" },
  { label: "GPT", value: "gpt" },
  { label: "Gemini", value: "gemini" },
  { label: "사내 생성기용", value: "internal" },
];
const DOC_TYPE_OPTIONS: { label: string; value: DocType }[] = [
  { label: "제안서", value: "제안서" },
  { label: "계획서", value: "계획서" },
  { label: "보고서", value: "보고서" },
  { label: "일반", value: "일반" },
];

const EMPTY_DRAFT = {
  id: "" as string | null,
  title: "",
  prompt_text: "",
  target: "general" as RetouchTarget,
  doc_type: undefined as DocType | undefined,
  // 테마(편집가능 .pptx/.docx 색·폰트). 빈 값이면 회사 기본.
  palette_primary: "",
  palette_accent: "",
  palette_text: "",
  heading_font: "",
  body_font: "",
};

export default function PromptLibraryPage() {
  const [tab, setTab] = useState<"mine" | "shared">("mine");
  const [query, setQuery] = useState("");
  const [mine, setMine] = useState<RetouchPreset[]>([]);
  const [shared, setShared] = useState<SharedRetouchPreset[]>([]);
  const [loading, setLoading] = useState(false);

  // 직접 작성/편집 모달. id 가 빈 문자열이면 신규.
  const [editorOpen, setEditorOpen] = useState(false);
  const [draft, setDraft] = useState({ ...EMPTY_DRAFT });
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      if (tab === "mine") setMine(await listRetouchPresets(query || undefined));
      else setShared(await listSharedRetouchPresets(query || undefined));
    } catch {
      message.error("프롬프트를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [tab, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const openNew = () => {
    setDraft({ ...EMPTY_DRAFT });
    setEditorOpen(true);
  };
  const openEdit = (p: RetouchPreset) => {
    setDraft({
      id: p.id,
      title: p.title,
      prompt_text: p.prompt_text,
      target: p.target,
      doc_type: (p.doc_type as DocType) ?? undefined,
      palette_primary: p.palette_primary ?? "",
      palette_accent: p.palette_accent ?? "",
      palette_text: p.palette_text ?? "",
      heading_font: p.heading_font ?? "",
      body_font: p.body_font ?? "",
    });
    setEditorOpen(true);
  };

  const handleSave = async () => {
    const hasTheme =
      draft.palette_primary ||
      draft.palette_accent ||
      draft.palette_text ||
      draft.heading_font ||
      draft.body_font;
    if (!draft.title.trim()) {
      message.warning("제목을 입력하세요");
      return;
    }
    if (!draft.prompt_text.trim() && !hasTheme) {
      message.warning("프롬프트 또는 테마(색·폰트) 중 하나는 채워주세요");
      return;
    }
    setSaving(true);
    // 빈 문자열은 null(해제)로 전송.
    const themeFields = {
      palette_primary: draft.palette_primary || null,
      palette_accent: draft.palette_accent || null,
      palette_text: draft.palette_text || null,
      heading_font: draft.heading_font.trim() || null,
      body_font: draft.body_font.trim() || null,
    };
    try {
      if (draft.id) {
        await updateRetouchPreset(draft.id, {
          title: draft.title.trim(),
          prompt_text: draft.prompt_text.trim(),
          ...themeFields,
        });
        message.success("수정했습니다");
      } else {
        await saveRetouchPreset({
          title: draft.title.trim(),
          prompt_text: draft.prompt_text.trim(),
          target: draft.target,
          doc_type: draft.doc_type ?? null,
          ...themeFields,
        });
        message.success("디자인 프리셋을 만들었습니다");
      }
      setEditorOpen(false);
      void load();
    } catch {
      message.error("저장에 실패했습니다");
    } finally {
      setSaving(false);
    }
  };

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

  const handleCopy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success("복사했습니다");
    } catch {
      message.error("복사에 실패했습니다");
    }
  };

  const preview = (t: string) => (t.length > 160 ? `${t.slice(0, 160)}…` : t);

  return (
    <div style={{ maxWidth: 1000 }}>
      <div
        style={{
          marginBottom: 16,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            디자인 라이브러리
          </h2>
          <Text type="secondary">
            문서 디자인 프리셋(프롬프트 + 색·폰트 테마)을 직접 만들고 보관·공유합니다. 문서
            만들기·리터치에서 골라 적용돼요.
          </Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>
          새 프리셋
        </Button>
      </div>

      <Input.Search
        allowClear
        placeholder="제목으로 검색"
        style={{ maxWidth: 320, marginBottom: 12 }}
        onSearch={(v) => setQuery(v.trim())}
      />

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as "mine" | "shared")}
        items={[
          {
            key: "mine",
            label: "내 프롬프트",
            children: (
              <List
                loading={loading && tab === "mine"}
                dataSource={mine}
                locale={{
                  emptyText: (
                    <Empty description="아직 만든 프리셋이 없습니다. ‘새 프리셋’으로 추가하세요." />
                  ),
                }}
                renderItem={(p) => (
                  <List.Item
                    actions={[
                      <Tooltip key="share" title="공유 — 다른 사용자도 사용 가능">
                        <Space size={4}>
                          <ShareAltOutlined style={{ color: "rgba(0,0,0,0.45)" }} />
                          <Switch
                            size="small"
                            checked={p.is_shared}
                            onChange={(v) => handleToggleShare(p.id, v)}
                          />
                        </Space>
                      </Tooltip>,
                      <Button
                        key="copy"
                        type="text"
                        size="small"
                        icon={<CopyOutlined />}
                        onClick={() => handleCopy(p.prompt_text)}
                      />,
                      <Button
                        key="edit"
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={() => openEdit(p)}
                      />,
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
                        <Space wrap>
                          <Text strong>{p.title}</Text>
                          {p.prompt_text?.trim() && <Tag bordered={false}>{p.target}</Tag>}
                          {(p.palette_primary || p.heading_font) && (
                            <Tag bordered={false} color="magenta">
                              🎨 테마
                            </Tag>
                          )}
                          {p.doc_type && (
                            <Tag bordered={false} color="geekblue">
                              {p.doc_type}
                            </Tag>
                          )}
                          {p.is_shared && (
                            <Tag bordered={false} color="blue">
                              공유 중
                            </Tag>
                          )}
                        </Space>
                      }
                      description={
                        <Paragraph type="secondary" style={{ fontSize: 12, margin: 0 }}>
                          {preview(p.prompt_text)}
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
            label: "공유 프롬프트",
            children: (
              <List
                loading={loading && tab === "shared"}
                dataSource={shared}
                locale={{
                  emptyText: <Empty description="공유된 프롬프트가 없습니다." />,
                }}
                renderItem={(p) => (
                  <List.Item
                    actions={[
                      <Button
                        key="copy"
                        type="text"
                        size="small"
                        icon={<CopyOutlined />}
                        onClick={() => handleCopy(p.prompt_text)}
                      />,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space wrap>
                          <Text strong>{p.title}</Text>
                          <Tag bordered={false}>{p.target}</Tag>
                          {p.is_mine && (
                            <Tag bordered={false} color="green">
                              내 프롬프트
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
                            {preview(p.prompt_text)}
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

      <Modal
        open={editorOpen}
        title={draft.id ? "디자인 프리셋 수정" : "새 디자인 프리셋"}
        okText="저장"
        cancelText="취소"
        confirmLoading={saving}
        onOk={handleSave}
        onCancel={() => setEditorOpen(false)}
        width={640}
      >
        <Space direction="vertical" size={12} style={{ width: "100%" }}>
          <Input
            placeholder="제목 (예: 임팩트 제안서 디자인)"
            value={draft.title}
            maxLength={300}
            onChange={(e) => setDraft((d) => ({ ...d, title: e.target.value }))}
          />
          <Space size={12} wrap>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                대상
              </Text>
              <Select
                style={{ width: 150 }}
                options={TARGET_OPTIONS}
                value={draft.target}
                disabled={!!draft.id}
                onChange={(v) => setDraft((d) => ({ ...d, target: v }))}
              />
            </Space>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                문서 종류
              </Text>
              <Select
                style={{ width: 130 }}
                allowClear
                placeholder="무관"
                options={DOC_TYPE_OPTIONS}
                value={draft.doc_type}
                disabled={!!draft.id}
                onChange={(v) => setDraft((d) => ({ ...d, doc_type: v }))}
              />
            </Space>
          </Space>
          <Input.TextArea
            placeholder="프롬프트 본문(선택) — 원하는 디자인·구성·톤 방향을 자유롭게 적으세요. HTML 디자인 덱·외부 AI·내부 재생성에 쓰입니다."
            value={draft.prompt_text}
            autoSize={{ minRows: 6, maxRows: 18 }}
            onChange={(e) => setDraft((d) => ({ ...d, prompt_text: e.target.value }))}
            style={{ fontSize: 13 }}
          />

          <Divider style={{ margin: "4px 0" }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              테마 (편집가능 PPT/Word 색·폰트 — 선택, 비우면 회사 기본)
            </Text>
          </Divider>
          <Space size={16} wrap>
            {(
              [
                ["주색", "palette_primary"],
                ["강조색", "palette_accent"],
                ["글자색", "palette_text"],
              ] as const
            ).map(([label, key]) => (
              <Space key={key} size={6}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {label}
                </Text>
                <ColorPicker
                  allowClear
                  value={draft[key] || undefined}
                  onChange={(_, hex) => setDraft((d) => ({ ...d, [key]: hex }))}
                  onClear={() => setDraft((d) => ({ ...d, [key]: "" }))}
                />
              </Space>
            ))}
          </Space>
          <Space size={16} wrap>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                제목 폰트
              </Text>
              <Input
                style={{ width: 150 }}
                placeholder="예: Pretendard"
                value={draft.heading_font}
                onChange={(e) => setDraft((d) => ({ ...d, heading_font: e.target.value }))}
              />
            </Space>
            <Space size={6}>
              <Text type="secondary" style={{ fontSize: 12 }}>
                본문 폰트
              </Text>
              <Input
                style={{ width: 150 }}
                placeholder="예: Pretendard"
                value={draft.body_font}
                onChange={(e) => setDraft((d) => ({ ...d, body_font: e.target.value }))}
              />
            </Space>
          </Space>
          <Text type="secondary" style={{ fontSize: 11 }}>
            ※ 색은 표지·제목바·차트·강조에 적용됩니다. 폰트는 문서를 여는 PC에 설치돼 있어야
            보입니다(없으면 대체 폰트). 좌표·마스트헤드 같은 레이아웃은 HTML 덱에서만 가능합니다.
          </Text>
        </Space>
      </Modal>
    </div>
  );
}
