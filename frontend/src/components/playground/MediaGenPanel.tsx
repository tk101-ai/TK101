import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { DownloadOutlined, PlayCircleOutlined } from "@ant-design/icons";
import {
  QUOTA_EXCEEDED_MESSAGE,
  createImageTask,
  createVideoFromMedia,
  createVideoTask,
  describeTask,
  getMediaModels,
  getMyMedia,
  isQuotaExceededError,
  mediaFileUrl,
} from "../../api/playground";
import type {
  PlaygroundAttachment,
  PlaygroundMediaItem,
  PlaygroundMediaModelOption,
  PlaygroundTaskStatus,
} from "../../api/playground";
import BaseImagePicker from "./BaseImagePicker";
import QuotaIndicator from "./QuotaIndicator";
import { triggerBlobDownload } from "../../utils/download";

const { Text, Paragraph } = Typography;

type MediaKind = "image" | "video";

interface MediaGenPanelProps {
  kind: MediaKind;
}

interface ActiveTask {
  // DB row 의 id (있으면 안정 URL 서빙 가능).
  mediaId: string | null;
  taskId: string;
  kind: MediaKind;
  prompt: string;
  modelKey: string;
  status: PlaygroundTaskStatus["status"];
  outputUrl: string | null;
  errorMessage: string | null;
  costUsd: number | null;
  // 생성 시각 (ISO). DB 복원 시 created_at, 신규 요청 시 클라이언트 now.
  createdAt: string;
}

function itemToTask(item: PlaygroundMediaItem): ActiveTask {
  return {
    mediaId: item.id,
    taskId: item.task_id ?? item.id,
    kind: item.media_type,
    prompt: item.prompt ?? "",
    modelKey: item.model_key ?? "",
    status: item.status,
    outputUrl: item.file_path ? mediaFileUrl(item.id) : item.url,
    errorMessage: item.error_message,
    costUsd: item.cost_usd,
    createdAt: item.created_at,
  };
}

/** 로컬 타임존 기준 YYYY-MM-DD 문자열. */
function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** dateKey(YYYY-MM-DD) → "오늘 / 어제 / YYYY-MM-DD" 헤더 라벨. */
function dateGroupLabel(dateKey: string): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dateKey === toDateKey(today)) return "오늘";
  if (dateKey === toDateKey(yesterday)) return "어제";
  return dateKey;
}

interface DateGroup {
  dateKey: string;
  label: string;
  tasks: ActiveTask[];
}

/**
 * task 목록을 생성 날짜(로컬 타임존)별로 그룹핑. 최신 날짜가 먼저, 각 그룹 내에서도
 * 입력 순서(최신순)를 유지한다. createdAt 파싱 실패 항목은 "오늘" 그룹에 둔다.
 */
function groupTasksByDate(tasks: ActiveTask[]): DateGroup[] {
  const todayKey = toDateKey(new Date());
  const order: string[] = [];
  const buckets = new Map<string, ActiveTask[]>();
  for (const t of tasks) {
    const parsed = t.createdAt ? new Date(t.createdAt) : null;
    const key =
      parsed && !Number.isNaN(parsed.getTime()) ? toDateKey(parsed) : todayKey;
    if (!buckets.has(key)) {
      buckets.set(key, []);
      order.push(key);
    }
    buckets.get(key)!.push(t);
  }
  // 최신 날짜 우선 정렬.
  order.sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  return order.map((dateKey) => ({
    dateKey,
    label: dateGroupLabel(dateKey),
    tasks: buckets.get(dateKey)!,
  }));
}

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MS = 5 * 60 * 1000;

const STATUS_COLOR: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "default",
  running: "processing",
  succeeded: "success",
  failed: "error",
  unknown: "warning",
};

const STATUS_LABEL: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "대기 중",
  running: "생성 중",
  succeeded: "완료",
  failed: "실패",
  unknown: "알 수 없음",
};

const ASPECT_RATIO_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "1:1", label: "1:1 (정사각)" },
  { value: "16:9", label: "16:9 (와이드)" },
  { value: "9:16", label: "9:16 (세로)" },
  { value: "4:3", label: "4:3" },
  { value: "3:4", label: "3:4" },
];

const VIDEO_RESOLUTION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "720P", label: "720P" },
  { value: "1080P", label: "1080P" },
];

/**
 * 이미지·영상 생성 공통 패널 (T8 Phase 4/5 뼈대).
 *
 * - 백엔드 `/api/playground/{image|video}` 호출 → task_id 수신
 * - 3초 간격 폴링으로 결과 URL 확보 (최대 5분)
 * - DB 영속화 없음. 새로고침하면 진행 중 task 목록은 사라짐.
 * - admin 전용 (라우터 단에서 가드).
 */
export default function MediaGenPanel({ kind }: MediaGenPanelProps) {
  const [form] = Form.useForm();
  const [models, setModels] = useState<PlaygroundMediaModelOption[]>([]);
  const [videoModels, setVideoModels] = useState<PlaygroundMediaModelOption[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
  const [quotaRefreshKey, setQuotaRefreshKey] = useState(0);
  const [i2vTarget, setI2vTarget] = useState<ActiveTask | null>(null);
  const [baseImage, setBaseImage] = useState<PlaygroundAttachment | null>(null);
  const pollersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  // 1) 모델 카탈로그 fetch + 본인 기존 미디어 갤러리 로드 (새로고침 후 복원).
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const [models, history] = await Promise.all([
          getMediaModels(),
          getMyMedia(kind, 30),
        ]);
        if (cancelled) return;
        const list = kind === "image" ? models.image : models.video;
        setModels(list);
        // 영상 모델은 image kind 일 때 i2v 모달에서 사용.
        setVideoModels(models.video);
        if (list[0]) {
          form.setFieldValue("model_key", list[0].key);
        }
        // DB에서 받아온 본인 미디어 → 최신순으로 카드 표시.
        setTasks(history.map(itemToTask));
        // 아직 running/pending 상태인 항목은 다시 폴링 등록.
        for (const item of history) {
          if (item.status === "pending" || item.status === "running") {
            if (item.task_id) startPolling(item.task_id);
          }
        }
      } catch {
        // 권한/네트워크 실패 — 빈 목록 유지.
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind]);

  // 2) 컴포넌트 unmount 시 폴링 정리.
  useEffect(() => {
    return () => {
      for (const id of pollersRef.current.values()) clearInterval(id);
      pollersRef.current.clear();
    };
  }, []);

  const defaultModelKey = useMemo(() => models[0]?.key, [models]);

  // 결과물을 생성 날짜별로 그룹핑 (오늘 / 어제 / YYYY-MM-DD 섹션).
  const dateGroups = useMemo(() => groupTasksByDate(tasks), [tasks]);

  const startPolling = (taskId: string) => {
    const startedAt = Date.now();
    const poll = async () => {
      try {
        const status = await describeTask(kind, taskId);
        setTasks((prev) =>
          prev.map((t) =>
            t.taskId === taskId
              ? {
                  ...t,
                  status: status.status,
                  outputUrl: status.output_url,
                  errorMessage: status.error_message,
                  // 폴링 응답의 media_id 로 mediaId 갱신 — 신규 생성 task 도
                  // 폴링 완료 시 다운로드 버튼이 안정 URL 을 쓸 수 있게.
                  mediaId: status.media_id ?? t.mediaId,
                }
              : t,
          ),
        );
        if (status.status === "succeeded" || status.status === "failed") {
          const id = pollersRef.current.get(taskId);
          if (id) clearInterval(id);
          pollersRef.current.delete(taskId);
        }
      } catch (err: unknown) {
        // 폴링 중 일시 오류는 무시 (다음 tick에서 재시도).
        if (Date.now() - startedAt > POLL_MAX_MS) {
          const id = pollersRef.current.get(taskId);
          if (id) clearInterval(id);
          pollersRef.current.delete(taskId);
          setTasks((prev) =>
            prev.map((t) =>
              t.taskId === taskId
                ? {
                    ...t,
                    status: "failed",
                    errorMessage:
                      err instanceof Error ? err.message : "폴링 타임아웃",
                  }
                : t,
            ),
          );
        }
      }
    };
    void poll();
    const handle = setInterval(poll, POLL_INTERVAL_MS);
    pollersRef.current.set(taskId, handle);
  };

  const onSubmit = async (values: Record<string, unknown>) => {
    setSubmitting(true);
    try {
      let res;
      if (kind === "image") {
        res = await createImageTask({
          prompt: String(values.prompt),
          model_key: String(values.model_key ?? defaultModelKey ?? ""),
          negative_prompt:
            typeof values.negative_prompt === "string" && values.negative_prompt
              ? values.negative_prompt
              : null,
          aspect_ratio: String(values.aspect_ratio ?? "1:1"),
          enhance_prompt: Boolean(values.enhance_prompt ?? true),
          reference_attachment_id: baseImage?.id ?? null,
        });
      } else {
        res = await createVideoTask({
          prompt: String(values.prompt),
          model_key: String(values.model_key ?? defaultModelKey ?? ""),
          duration: Number(values.duration ?? 5),
          resolution: String(values.resolution ?? "720P"),
          aspect_ratio: String(values.aspect_ratio ?? "16:9"),
          audio_generation: Boolean(values.audio_generation ?? false),
          enhance_prompt: Boolean(values.enhance_prompt ?? true),
          reference_attachment_id: baseImage?.id ?? null,
        });
      }

      setTasks((prev) => [
        {
          mediaId: null,
          taskId: res.task_id,
          kind,
          prompt: String(values.prompt),
          modelKey: String(values.model_key ?? defaultModelKey ?? ""),
          status: "pending",
          outputUrl: null,
          errorMessage: null,
          costUsd: null,
          createdAt: new Date().toISOString(),
        },
        ...prev,
      ]);
      startPolling(res.task_id);
      message.success(`${kind === "image" ? "이미지" : "영상"} 생성 요청 접수`);
      setQuotaRefreshKey((k) => k + 1);
    } catch (err: unknown) {
      if (isQuotaExceededError(err)) {
        message.error(QUOTA_EXCEEDED_MESSAGE);
      } else {
        const msg = err instanceof Error ? err.message : "요청 실패";
        message.error(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleI2VSubmit = async (
    values: {
      prompt: string;
      model_key: string;
      duration: number;
      resolution: string;
      aspect_ratio: string;
      audio_generation: boolean;
      enhance_prompt: boolean;
    },
    target: ActiveTask,
  ) => {
    if (!target.mediaId) {
      message.error("이미지 ID를 찾을 수 없습니다 (DB 영속 안 됨)");
      return;
    }
    try {
      await createVideoFromMedia({
        prompt: values.prompt,
        image_media_id: target.mediaId,
        model_key: values.model_key,
        duration: values.duration,
        resolution: values.resolution,
        aspect_ratio: values.aspect_ratio,
        audio_generation: values.audio_generation,
        enhance_prompt: values.enhance_prompt,
      });
      message.success("영상 생성 작업 시작 — Video Gen 탭에서 확인하세요");
      setI2vTarget(null);
      setQuotaRefreshKey((k) => k + 1);
    } catch (err: unknown) {
      if (isQuotaExceededError(err)) {
        message.error(QUOTA_EXCEEDED_MESSAGE);
      } else {
        // 백엔드 503/400 등의 detail 메시지 우선 노출 — 텐센트 i2v raw 오류 그대로 보임.
        const detail =
          (err as { response?: { data?: { detail?: string } }; message?: string })
            ?.response?.data?.detail ||
          (err as Error)?.message ||
          "영상 생성 요청 실패";
        message.error(`영상 생성 실패: ${detail}`);
      }
    }
  };

  return (
    <div style={{ display: "flex", gap: 16 }}>
      {/* 좌: 입력 폼 + 한도 표시 */}
      <div style={{ width: 420, flexShrink: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        <QuotaIndicator refreshKey={quotaRefreshKey} />
      <Card size="small">

        <Form
          form={form}
          layout="vertical"
          onFinish={onSubmit}
          initialValues={
            kind === "image"
              ? { aspect_ratio: "1:1", enhance_prompt: true }
              : {
                  aspect_ratio: "16:9",
                  resolution: "720P",
                  duration: 5,
                  audio_generation: false,
                  enhance_prompt: true,
                }
          }
        >
          <Form.Item label="베이스 이미지 (선택)">
            <BaseImagePicker
              value={baseImage}
              onChange={setBaseImage}
              pendingNotice={
                baseImage
                  ? "베이스 기반 생성은 텐센트 API spec 확인 후 활성화됩니다. 지금 '생성'을 누르면 503 안내가 표시됩니다 — 베이스 없이 생성하려면 위에서 제거"
                  : undefined
              }
            />
          </Form.Item>

          <Form.Item
            name="prompt"
            label="프롬프트"
            rules={[{ required: true, message: "프롬프트는 필수" }]}
          >
            <Input.TextArea
              rows={4}
              placeholder={
                kind === "image"
                  ? baseImage
                    ? "예: 베이스 이미지를 깔끔한 제품 스타일로 재해석"
                    : "예: A clean product-style capybara mascot, studio lighting"
                  : baseImage
                    ? "예: 베이스 이미지의 캐릭터가 가볍게 움직이는 짧은 영상"
                    : "예: A capybara mascot moves gently in a short studio video"
              }
            />
          </Form.Item>

          <Form.Item name="model_key" label="모델">
            <Select
              options={models.map((m) => ({
                value: m.key,
                label: m.badge ? `${m.label} (${m.badge})` : m.label,
              }))}
              placeholder={
                models.length === 0 ? "모델 목록 로딩 중…" : "모델을 선택하세요"
              }
            />
          </Form.Item>

          <Form.Item name="aspect_ratio" label="화면 비율">
            <Select options={ASPECT_RATIO_OPTIONS} />
          </Form.Item>

          {kind === "image" && (
            <Form.Item name="negative_prompt" label="네거티브 프롬프트 (선택)">
              <Input.TextArea
                rows={2}
                placeholder="예: low quality, blurry, distorted"
              />
            </Form.Item>
          )}

          {kind === "video" && (
            <>
              <Form.Item name="duration" label="영상 길이 (초)">
                <InputNumber min={1} max={60} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="resolution" label="해상도">
                <Select options={VIDEO_RESOLUTION_OPTIONS} />
              </Form.Item>
              <Form.Item
                name="audio_generation"
                label="오디오 생성"
                valuePropName="checked"
              >
                <Switch />
              </Form.Item>
            </>
          )}

          <Form.Item
            name="enhance_prompt"
            label="프롬프트 자동 보강"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>

          <Button type="primary" htmlType="submit" loading={submitting} block>
            {kind === "image" ? "이미지 생성" : "영상 생성"}
          </Button>
        </Form>
      </Card>
      </div>

      {/* 우: 작업 목록 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {tasks.length === 0 ? (
          <Alert
            type="info"
            showIcon
            message="아직 생성 요청이 없습니다"
            description="왼쪽 폼에서 프롬프트를 입력하고 생성 버튼을 누르세요. 결과는 텐센트 임시 스토리지 URL로 반환되며, 페이지를 새로고침하면 진행 중 작업 목록은 사라집니다 (뼈대 단계)."
          />
        ) : (
          <Space direction="vertical" size={20} style={{ width: "100%" }}>
            {dateGroups.map((group) => (
              <div key={group.dateKey}>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginBottom: 10,
                  }}
                >
                  <Text
                    strong
                    style={{
                      fontSize: 12,
                      letterSpacing: "0.04em",
                      color: "rgba(0,0,0,0.65)",
                    }}
                  >
                    {group.label}
                  </Text>
                  <Tag style={{ margin: 0 }}>{group.tasks.length}</Tag>
                  <div
                    style={{
                      flex: 1,
                      height: 1,
                      background: "rgba(0,0,0,0.06)",
                    }}
                  />
                </div>
                <Space direction="vertical" size={12} style={{ width: "100%" }}>
                  {group.tasks.map((t) => (
                    <TaskCard
                      key={t.taskId}
                      task={t}
                      onConvertToVideo={
                        kind === "image" ? () => setI2vTarget(t) : undefined
                      }
                    />
                  ))}
                </Space>
              </div>
            ))}
          </Space>
        )}
      </div>

      {/* I2V 모달 — image kind 에서만 사용 */}
      <I2VModal
        target={i2vTarget}
        videoModels={videoModels}
        onCancel={() => setI2vTarget(null)}
        onSubmit={handleI2VSubmit}
      />
    </div>
  );
}

/**
 * 결과물(이미지/영상)을 사용자 PC 로 즉시 다운로드.
 *
 * - mediaId 가 있으면 백엔드 안정 URL(`/api/playground/media/{id}/file`) 사용 — same-origin
 *   이라 fetch + Blob 다 통과. 백엔드 디스크에 영구 보관된 파일이라 만료 위험도 없음.
 * - mediaId 없으면 텐센트 임시 URL 로 fallback. cross-origin 차단 시 새 탭으로.
 */
async function downloadTaskOutput(task: ActiveTask): Promise<void> {
  const ext = task.kind === "image" ? "png" : "mp4";
  const safeModel = (task.modelKey || "media").replace(/[^a-zA-Z0-9_.-]/g, "_");
  const filename = `${safeModel}_${task.taskId.slice(0, 12)}.${ext}`;

  // 1) 안정 URL — 백엔드 stream 통해 다운로드.
  if (task.mediaId) {
    try {
      const res = await fetch(`/api/playground/media/${task.mediaId}/file`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      triggerBlobDownload(blob, filename);
      return;
    } catch (err) {
      // fall through 텐센트 URL 시도.
      console.warn("백엔드 미디어 fetch 실패, 텐센트 URL 로 fallback", err);
    }
  }

  // 2) 텐센트 임시 URL fallback — cross-origin CORS 허용되면 fetch+blob, 아니면 새 탭.
  if (!task.outputUrl) {
    message.error("다운로드 URL 이 없습니다");
    return;
  }
  try {
    const res = await fetch(task.outputUrl);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    triggerBlobDownload(blob, filename);
  } catch {
    // CORS 거부 시 — 그냥 새 탭 열어서 사용자가 브라우저 다운로드 사용.
    window.open(task.outputUrl, "_blank", "noopener,noreferrer");
  }
}

function TaskCard({
  task,
  onConvertToVideo,
}: {
  task: ActiveTask;
  onConvertToVideo?: () => void;
}) {
  // i2v 버튼 노출 조건: image kind + 성공 + DB persist 된 mediaId 존재.
  const canConvert =
    Boolean(onConvertToVideo) &&
    task.kind === "image" &&
    task.status === "succeeded" &&
    Boolean(task.mediaId);
  return (
    <Card
      size="small"
      title={
        <Space>
          <Tag color={STATUS_COLOR[task.status]}>{STATUS_LABEL[task.status]}</Tag>
          <Text code style={{ fontSize: 11 }}>
            {task.modelKey}
          </Text>
          {task.costUsd !== null && task.costUsd !== undefined && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              {/* 백엔드 Decimal 은 JSON 직렬화 시 string 으로 옴 — Number() 강제 변환 후 toFixed. */}
              ${Number(task.costUsd).toFixed(4)}
            </Text>
          )}
        </Space>
      }
      extra={
        <Text code style={{ fontSize: 10, color: "rgba(0,0,0,0.45)" }}>
          {task.taskId.slice(0, 12)}…
        </Text>
      }
    >
      <Paragraph style={{ marginBottom: 8, fontSize: 12 }} type="secondary">
        {task.prompt}
      </Paragraph>

      {task.status === "succeeded" && task.outputUrl && (
        <div style={{ marginTop: 8 }}>
          {task.kind === "image" ? (
            <img
              src={task.outputUrl}
              alt="generated"
              style={{
                maxWidth: "100%",
                borderRadius: 6,
                border: "1px solid rgba(0,0,0,0.08)",
              }}
            />
          ) : (
            <video
              src={task.outputUrl}
              controls
              style={{ maxWidth: "100%", borderRadius: 6 }}
            />
          )}
          <div
            style={{
              marginTop: 6,
              display: "flex",
              gap: 8,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <Button
              size="small"
              type="primary"
              icon={<DownloadOutlined />}
              onClick={() => downloadTaskOutput(task)}
            >
              다운로드
            </Button>
            {canConvert && (
              <Tooltip title="텐센트 i2v API spec 확정 전 — 임시 비활성. 텐센트 담당자에게 정확한 호출 spec 문의 필요.">
                <Button
                  size="small"
                  icon={<PlayCircleOutlined />}
                  onClick={onConvertToVideo}
                  disabled
                >
                  이 이미지로 영상 (준비 중)
                </Button>
              </Tooltip>
            )}
          </div>
        </div>
      )}

      {task.status === "failed" && (
        <Alert
          type="error"
          showIcon
          message="생성 실패"
          description={task.errorMessage ?? "텐센트가 명시한 사유 없음"}
        />
      )}
    </Card>
  );
}

interface I2VFormValues {
  prompt: string;
  model_key: string;
  duration: number;
  resolution: string;
  aspect_ratio: string;
  audio_generation: boolean;
  enhance_prompt: boolean;
}

function I2VModal({
  target,
  videoModels,
  onCancel,
  onSubmit,
}: {
  target: ActiveTask | null;
  videoModels: PlaygroundMediaModelOption[];
  onCancel: () => void;
  onSubmit: (values: I2VFormValues, target: ActiveTask) => Promise<void>;
}) {
  const [form] = Form.useForm<I2VFormValues>();
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (target) {
      form.setFieldsValue({
        prompt: target.prompt,
        model_key: videoModels[0]?.key ?? "",
        duration: 5,
        resolution: "720P",
        aspect_ratio: "16:9",
        audio_generation: false,
        enhance_prompt: true,
      });
    }
    // 닫힐 때 form 초기화는 destroyOnClose 가 처리.
  }, [target, videoModels, form]);

  const handleOk = async () => {
    if (!target) return;
    try {
      const values = await form.validateFields();
      setSubmitting(true);
      await onSubmit(values, target);
    } catch {
      // validation error — 모달 유지.
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="이 이미지로 영상 만들기"
      open={target !== null}
      onCancel={onCancel}
      onOk={() => void handleOk()}
      okText="영상 생성"
      cancelText="취소"
      confirmLoading={submitting}
      destroyOnClose
      width={520}
    >
      {target?.outputUrl && (
        <div style={{ marginBottom: 12, textAlign: "center" }}>
          <img
            src={target.outputUrl}
            alt="source"
            style={{
              maxWidth: "100%",
              maxHeight: 200,
              borderRadius: 6,
              border: "1px solid rgba(0,0,0,0.08)",
            }}
          />
        </div>
      )}
      <Form form={form} layout="vertical" preserve={false}>
        <Form.Item
          name="prompt"
          label="영상 프롬프트"
          rules={[{ required: true, message: "프롬프트를 입력하세요" }]}
        >
          <Input.TextArea rows={3} placeholder="예: 카메라가 천천히 줌인하며 캐릭터가 미소 짓는다" />
        </Form.Item>
        <Form.Item
          name="model_key"
          label="영상 모델"
          rules={[{ required: true, message: "모델을 선택하세요" }]}
        >
          <Select
            options={videoModels.map((m) => ({
              value: m.key,
              label: m.badge ? `${m.label} (${m.badge})` : m.label,
            }))}
            placeholder={
              videoModels.length === 0 ? "모델 목록 로딩 중…" : "모델을 선택하세요"
            }
          />
        </Form.Item>
        <Form.Item name="duration" label="영상 길이 (초)">
          <InputNumber min={1} max={60} style={{ width: "100%" }} />
        </Form.Item>
        <Form.Item name="resolution" label="해상도">
          <Select options={VIDEO_RESOLUTION_OPTIONS} />
        </Form.Item>
        <Form.Item name="aspect_ratio" label="화면 비율">
          <Select options={ASPECT_RATIO_OPTIONS} />
        </Form.Item>
        <Form.Item name="audio_generation" label="오디오 생성" valuePropName="checked">
          <Switch />
        </Form.Item>
        <Form.Item
          name="enhance_prompt"
          label="프롬프트 자동 보강"
          valuePropName="checked"
        >
          <Switch />
        </Form.Item>
      </Form>
    </Modal>
  );
}
