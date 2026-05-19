import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from "antd";
import {
  createImageTask,
  createVideoTask,
  describeTask,
  getMediaModels,
  getMyMedia,
  mediaFileUrl,
} from "../../api/playground";
import type {
  PlaygroundMediaItem,
  PlaygroundMediaModelOption,
  PlaygroundTaskStatus,
} from "../../api/playground";

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
  };
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
  const [submitting, setSubmitting] = useState(false);
  const [tasks, setTasks] = useState<ActiveTask[]>([]);
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
        },
        ...prev,
      ]);
      startPolling(res.task_id);
      message.success(`${kind === "image" ? "이미지" : "영상"} 생성 요청 접수`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "요청 실패";
      message.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ display: "flex", gap: 16 }}>
      {/* 좌: 입력 폼 */}
      <Card size="small" style={{ width: 420, flexShrink: 0 }}>
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
          <Form.Item
            name="prompt"
            label="프롬프트"
            rules={[{ required: true, message: "프롬프트는 필수" }]}
          >
            <Input.TextArea
              rows={4}
              placeholder={
                kind === "image"
                  ? "예: A clean product-style capybara mascot, studio lighting"
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
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {tasks.map((t) => (
              <TaskCard key={t.taskId} task={t} />
            ))}
          </Space>
        )}
      </div>
    </div>
  );
}

function TaskCard({ task }: { task: ActiveTask }) {
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
              ${task.costUsd.toFixed(4)}
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
          <div style={{ marginTop: 6 }}>
            <a href={task.outputUrl} target="_blank" rel="noreferrer">
              원본 다운로드
            </a>
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
