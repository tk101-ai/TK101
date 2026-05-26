import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Tag,
  Timeline,
  Typography,
  message,
} from "antd";
import {
  ArrowLeftOutlined,
  CheckOutlined,
  CloseOutlined,
  DeleteOutlined,
  EditOutlined,
  FileOutlined,
  PaperClipOutlined,
  ReloadOutlined,
  SaveOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import {
  MESSAGE_STATUS_LABEL,
  MESSAGE_STATUS_TAG_COLOR,
  SESSION_STATUS_LABEL,
  SESSION_STATUS_TAG_COLOR,
  approveSession,
  deleteMessageAttachment,
  getSession,
  rejectSession,
  sendSessionNow,
  updateMessage,
  updateMessageTiming,
  uploadMessageAttachment,
  type MessageItem,
  type SessionDetail,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

/**
 * 세션 상세 + 메시지 타임라인 검수 화면 (T9 Phase C).
 *
 * - 상단 카드: 시나리오/발신·수신/상태/생성일/비용 + 상태별 액션 버튼.
 * - 타임라인: 메시지 1행씩, 인라인 편집 → `PATCH /messages/{id}`.
 * - 액션:
 *   - status=pending → [승인] / [거부]
 *   - status=approved → [지금 송신] / [거부로 변경]
 *   - status=sent → 송신 완료 안내만.
 */

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm:ss");
}

function formatCost(value: string | null): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `$${n.toFixed(4)}`;
}

function formatCumulativeOffset(sec: number): string {
  if (sec < 60) return `+${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (s === 0) return `+${m}m`;
  return `+${m}m ${s}s`;
}

/** send_after_sec 빠른 설정 프리셋. 라벨 = 사용자가 보는 텍스트, value = 초. */
const TIMING_PRESETS: { label: string; value: number }[] = [
  { label: "즉시", value: 0 },
  { label: "1분", value: 60 },
  { label: "5분", value: 300 },
  { label: "30분", value: 1800 },
  { label: "1시간", value: 3600 },
  { label: "3시간", value: 10800 },
  { label: "6시간", value: 21600 },
  { label: "12시간", value: 43200 },
];

interface TimingEditorProps {
  msg: MessageItem;
  disabled: boolean;
  onUpdated: (next: MessageItem) => void;
}

function TimingEditor({ msg, disabled, onUpdated }: TimingEditorProps) {
  const [editing, setEditing] = useState<boolean>(false);
  const [value, setValue] = useState<number>(msg.send_after_sec);
  const [saving, setSaving] = useState<boolean>(false);

  const submit = async (next: number) => {
    if (next < 0 || next > 86400) {
      message.warning("0초 ~ 24시간(86400초) 범위만 가능합니다.");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateMessageTiming(msg.id, next);
      message.success(`메시지 #${msg.order_index + 1} 텀 변경: +${next}s`);
      onUpdated(updated);
      setEditing(false);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "텀 변경 실패"));
    } finally {
      setSaving(false);
    }
  };

  if (disabled || msg.status === "sent") {
    return null;
  }

  if (!editing) {
    return (
      <Button
        size="small"
        type="link"
        style={{ padding: 0, fontSize: 12 }}
        onClick={() => {
          setValue(msg.send_after_sec);
          setEditing(true);
        }}
      >
        텀 변경
      </Button>
    );
  }

  return (
    <Space size={4} wrap style={{ fontSize: 12 }}>
      <InputNumber
        size="small"
        min={0}
        max={86400}
        value={value}
        onChange={(v) => setValue(typeof v === "number" ? v : 0)}
        disabled={saving}
        style={{ width: 80 }}
        addonAfter="초"
      />
      <Select
        size="small"
        value={undefined}
        placeholder="프리셋"
        options={TIMING_PRESETS.map((p) => ({ label: p.label, value: p.value }))}
        onChange={(v) => {
          if (typeof v === "number") setValue(v);
        }}
        style={{ width: 90 }}
        disabled={saving}
      />
      <Button
        size="small"
        type="primary"
        loading={saving}
        onClick={() => {
          void submit(value);
        }}
      >
        적용
      </Button>
      <Button
        size="small"
        onClick={() => setEditing(false)}
        disabled={saving}
      >
        취소
      </Button>
    </Space>
  );
}

interface MessageRowProps {
  msg: MessageItem;
  cumulativeOffset: number;
  onSaved: (next: MessageItem) => void;
  editingDisabled: boolean;
}

const ATTACHMENT_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.gif,.pdf,.xlsx,.xls,.csv,.hwp,.hwpx,.docx,.doc,.pptx,.ppt,.txt";

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

interface AttachmentBlockProps {
  msg: MessageItem;
  disabled: boolean;
  onChanged: (next: MessageItem) => void;
}

function AttachmentBlock({ msg, disabled, onChanged }: AttachmentBlockProps) {
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

function MessageRow({
  msg,
  cumulativeOffset,
  onSaved,
  editingDisabled,
}: MessageRowProps) {
  const [editing, setEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>("");
  const [saving, setSaving] = useState<boolean>(false);

  const display = msg.edited_content ?? msg.content;

  const startEdit = () => {
    setDraft(display);
    setEditing(true);
  };

  const cancelEdit = () => {
    setEditing(false);
    setDraft("");
  };

  const submitEdit = async () => {
    const trimmed = draft.trim();
    if (trimmed.length === 0) {
      message.warning("메시지 본문은 비울 수 없습니다.");
      return;
    }
    setSaving(true);
    try {
      const next = await updateMessage(msg.id, trimmed);
      message.success(`메시지 #${msg.order_index + 1} 저장됨`);
      onSaved(next);
      setEditing(false);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "메시지 저장 실패"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ marginBottom: 4 }}>
      <Space size={6} wrap style={{ marginBottom: 4 }}>
        <Text strong>{msg.sender_account_label}</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatCumulativeOffset(cumulativeOffset)}
        </Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          이전 메시지로부터 +{msg.send_after_sec}s
        </Text>
        <TimingEditor msg={msg} disabled={editingDisabled} onUpdated={onSaved} />
        <Tag color={MESSAGE_STATUS_TAG_COLOR[msg.status]}>
          {MESSAGE_STATUS_LABEL[msg.status]}
        </Tag>
        {msg.user_edited && (
          <Tag color="purple" icon={<EditOutlined />}>
            수정됨
          </Tag>
        )}
        {msg.sent_at && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            송신: {formatDateTime(msg.sent_at)}
          </Text>
        )}
      </Space>

      {editing ? (
        <div>
          <TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            autoSize={{ minRows: 2, maxRows: 8 }}
            maxLength={4096}
            showCount
            disabled={saving}
          />
          <Space style={{ marginTop: 8 }}>
            <Button
              type="primary"
              size="small"
              icon={<SaveOutlined />}
              loading={saving}
              onClick={() => {
                void submitEdit();
              }}
            >
              저장
            </Button>
            <Button size="small" onClick={cancelEdit} disabled={saving}>
              취소
            </Button>
          </Space>
        </div>
      ) : (
        <div
          onClick={() => {
            if (!editingDisabled) startEdit();
          }}
          style={{
            padding: "8px 12px",
            background: msg.user_edited ? "#f9f0ff" : "#fafafa",
            borderRadius: 6,
            border: "1px solid #f0f0f0",
            whiteSpace: "pre-wrap",
            cursor: editingDisabled ? "default" : "text",
          }}
          title={editingDisabled ? "송신 완료 상태에서는 편집할 수 없습니다" : "클릭하여 편집"}
        >
          {display}
        </div>
      )}
      <AttachmentBlock msg={msg} disabled={editingDisabled} onChanged={onSaved} />
    </div>
  );
}

interface ApproveModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onConfirm: (scheduledStart: string | null) => Promise<void>;
}

function ApproveModal({ open, loading, onClose, onConfirm }: ApproveModalProps) {
  const [scheduled, setScheduled] = useState<Dayjs | null>(null);

  useEffect(() => {
    if (!open) setScheduled(null);
  }, [open]);

  const handleOk = async () => {
    await onConfirm(scheduled ? scheduled.toISOString() : null);
  };

  return (
    <Modal
      title="세션 승인"
      open={open}
      onCancel={onClose}
      onOk={() => {
        void handleOk();
      }}
      okText="승인"
      cancelText="취소"
      confirmLoading={loading}
      destroyOnClose
    >
      <Paragraph>
        승인 후 워커가 픽업하여 송신합니다. 예약 시각을 비워두면 즉시 송신
        가능 상태로 전환됩니다.
      </Paragraph>
      <Form layout="vertical">
        <Form.Item label="예약 송신 시각 (선택)">
          <DatePicker
            showTime
            value={scheduled}
            onChange={setScheduled}
            style={{ width: "100%" }}
            format="YYYY-MM-DD HH:mm"
            placeholder="비워두면 즉시 송신 가능"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

interface RejectModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}

function RejectModal({ open, loading, onClose, onConfirm }: RejectModalProps) {
  const [reason, setReason] = useState<string>("");

  useEffect(() => {
    if (!open) setReason("");
  }, [open]);

  const handleOk = async () => {
    await onConfirm(reason.trim());
  };

  return (
    <Modal
      title="세션 거부"
      open={open}
      onCancel={onClose}
      onOk={() => {
        void handleOk();
      }}
      okText="거부"
      okType="danger"
      cancelText="취소"
      confirmLoading={loading}
      destroyOnClose
    >
      <Paragraph>거부 사유를 남기면 운영 로그에 기록됩니다 (선택).</Paragraph>
      <TextArea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        autoSize={{ minRows: 3, maxRows: 6 }}
        maxLength={500}
        showCount
        placeholder="예: 톤 어색함, 가격 정보 오타"
      />
    </Modal>
  );
}

export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [approveOpen, setApproveOpen] = useState<boolean>(false);
  const [rejectOpen, setRejectOpen] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [sendNowLoading, setSendNowLoading] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const next = await getSession(id);
      setDetail(next);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 상세 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  const session = detail?.session ?? null;
  const messages = useMemo(() => detail?.messages ?? [], [detail]);

  // 누적 send_after_sec — 메시지 순서대로 합산.
  const cumulativeOffsets = useMemo(() => {
    const offsets: number[] = [];
    let acc = 0;
    for (const msg of messages) {
      acc += msg.send_after_sec;
      offsets.push(acc);
    }
    return offsets;
  }, [messages]);

  const handleMessageSaved = useCallback((next: MessageItem) => {
    setDetail((current) => {
      if (!current) return current;
      return {
        ...current,
        messages: current.messages.map((m) => (m.id === next.id ? next : m)),
      };
    });
  }, []);

  const handleApprove = async (scheduledStart: string | null) => {
    if (!session) return;
    setActionLoading(true);
    try {
      await approveSession(session.id, scheduledStart);
      message.success("세션을 승인했습니다.");
      setApproveOpen(false);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "승인 실패"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (reason: string) => {
    if (!session) return;
    setActionLoading(true);
    try {
      await rejectSession(session.id, reason.length > 0 ? reason : undefined);
      message.success("세션을 거부했습니다.");
      setRejectOpen(false);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "거부 실패"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendNow = async () => {
    if (!session) return;
    setSendNowLoading(true);
    try {
      const res = await sendSessionNow(session.id);
      // 부분 실패라도 res.error 가 있으면 사용자에게 첫 실패 원인 같이 노출.
      if (res.status === "failed") {
        Modal.error({
          title: `송신 실패 (${res.failed_count}건 실패 / ${res.sent_count}건 성공)`,
          content: res.error ?? "알 수 없는 오류 — 서버 로그를 확인하세요.",
          width: 600,
        });
      } else if (res.failed_count > 0) {
        Modal.warning({
          title: `부분 성공 (${res.sent_count}건 송신 / ${res.failed_count}건 실패)`,
          content: res.error ?? "일부 메시지 실패 — 검수 화면에서 확인하세요.",
          width: 600,
        });
      } else if (res.status === "sent") {
        message.success(`송신 완료 — ${res.sent_count}건`);
      } else {
        message.info(`상태: ${SESSION_STATUS_LABEL[res.status]}`);
      }
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "송신 실패"));
    } finally {
      setSendNowLoading(false);
    }
  };

  if (!id) {
    return <Empty description="세션 ID 가 없습니다" />;
  }

  if (loading && !detail) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!session) {
    return (
      <div style={{ maxWidth: 720 }}>
        <Empty description="세션을 찾을 수 없습니다" />
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <Link to="/distribution/sessions">
            <Button icon={<ArrowLeftOutlined />}>목록으로</Button>
          </Link>
        </div>
      </div>
    );
  }

  const status = session.status;
  const editingDisabled = status === "sent" || status === "sending";

  return (
    <div style={{ maxWidth: 1080 }}>
      <div style={{ marginBottom: 16 }}>
        <Link to="/distribution/sessions">
          <Button type="link" icon={<ArrowLeftOutlined />} style={{ paddingLeft: 0 }}>
            목록으로
          </Button>
        </Link>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          세션 상세
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          메시지 본문을 클릭해 편집한 뒤 승인 또는 즉시 송신할 수 있습니다.
        </Paragraph>
      </div>

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <Text strong>{session.scenario_name}</Text>
            <Tag color={SESSION_STATUS_TAG_COLOR[status]}>
              {SESSION_STATUS_LABEL[status]}
            </Tag>
          </Space>
        }
        extra={
          <Space wrap>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void fetchData();
              }}
            >
              새로고침
            </Button>
            {status === "pending" && (
              <>
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  onClick={() => setApproveOpen(true)}
                >
                  승인
                </Button>
                <Button
                  danger
                  icon={<CloseOutlined />}
                  onClick={() => setRejectOpen(true)}
                >
                  거부
                </Button>
              </>
            )}
            {status === "approved" && (
              <>
                <Popconfirm
                  title="지금 바로 송신할까요?"
                  description="송신 결과가 즉시 반영됩니다."
                  okText="송신"
                  cancelText="취소"
                  onConfirm={() => {
                    void handleSendNow();
                  }}
                >
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={sendNowLoading}
                  >
                    지금 송신
                  </Button>
                </Popconfirm>
                <Button
                  danger
                  icon={<StopOutlined />}
                  onClick={() => setRejectOpen(true)}
                >
                  거부로 변경
                </Button>
              </>
            )}
          </Space>
        }
      >
        <Descriptions size="small" column={2} bordered>
          <Descriptions.Item label="발신">
            {session.sender_account_label}
          </Descriptions.Item>
          <Descriptions.Item label="수신">
            {session.receiver_account_label}
          </Descriptions.Item>
          <Descriptions.Item label="메시지 수">
            {session.message_count}
          </Descriptions.Item>
          <Descriptions.Item label="비용 (USD)">
            {formatCost(session.llm_cost_usd)}
          </Descriptions.Item>
          <Descriptions.Item label="생성일">
            {formatDateTime(session.generated_at)}
          </Descriptions.Item>
          <Descriptions.Item label="승인일">
            {formatDateTime(session.approved_at)}
          </Descriptions.Item>
          <Descriptions.Item label="예약 송신">
            {formatDateTime(session.scheduled_start)}
          </Descriptions.Item>
          <Descriptions.Item label="완료일">
            {formatDateTime(session.completed_at)}
          </Descriptions.Item>
        </Descriptions>

        {session.scenario_attachment_required && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message="이 시나리오는 파일 첨부가 권장됩니다 (예: VIP 프로모션 — 엑셀)"
            description={(() => {
              const total = messages.length;
              const withAttachment = messages.filter(
                (m) => m.attachment_url != null,
              ).length;
              if (total === 0) return "메시지가 없습니다.";
              if (withAttachment === 0) {
                return `숫자·상세 정보는 엑셀로만 전달하는 것이 시나리오 취지입니다. 현재 첨부된 메시지가 없습니다 (${total}건 중 0건). 송신 전 1건 이상에 엑셀 파일을 첨부하세요.`;
              }
              return `현재 ${total}건 중 ${withAttachment}건에 첨부가 포함되어 있습니다.`;
            })()}
          />
        )}
        {status === "sent" && (
          <Alert
            type="success"
            showIcon
            style={{ marginTop: 16 }}
            message="송신이 완료된 세션입니다."
            description="이 세션은 더 이상 편집할 수 없습니다."
          />
        )}
        {status === "failed" && (
          <Alert
            type="error"
            showIcon
            style={{ marginTop: 16 }}
            message="송신에 실패한 세션입니다."
            description="문제 메시지를 확인한 뒤 필요 시 재승인하거나 거부 처리하세요."
          />
        )}
        {status === "rejected" && (
          <Alert
            type="info"
            showIcon
            style={{ marginTop: 16 }}
            message="거부된 세션입니다."
          />
        )}
        {status === "sending" && (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message="송신이 진행 중입니다."
            description="워커가 작업을 끝낼 때까지 편집·재승인은 권장하지 않습니다."
          />
        )}
      </Card>

      <Card title="메시지 타임라인" size="small">
        {messages.length === 0 ? (
          <Empty description="메시지가 없습니다" />
        ) : (
          <Timeline
            items={messages.map((msg, idx) => ({
              color: msg.status === "sent" ? "green" : msg.status === "failed" ? "red" : "blue",
              children: (
                <MessageRow
                  key={msg.id}
                  msg={msg}
                  cumulativeOffset={cumulativeOffsets[idx] ?? 0}
                  onSaved={handleMessageSaved}
                  editingDisabled={editingDisabled}
                />
              ),
            }))}
          />
        )}
      </Card>

      <ApproveModal
        open={approveOpen}
        loading={actionLoading}
        onClose={() => setApproveOpen(false)}
        onConfirm={handleApprove}
      />

      <RejectModal
        open={rejectOpen}
        loading={actionLoading}
        onClose={() => setRejectOpen(false)}
        onConfirm={handleReject}
      />

    </div>
  );
}
