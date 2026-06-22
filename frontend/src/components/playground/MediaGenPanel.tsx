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
  QUOTA_EXCEEDED_MESSAGE,
  createImageTask,
  createVideoFromMedia,
  createVideoTask,
  describeTask,
  getMediaModels,
  getMyMedia,
  isQuotaExceededError,
} from "../../api/playground";
import type {
  PlaygroundAttachment,
  PlaygroundMediaModelOption,
} from "../../api/playground";
import BaseImagePicker from "./BaseImagePicker";
import QuotaIndicator from "./QuotaIndicator";
import {
  ASPECT_RATIO_OPTIONS,
  POLL_INTERVAL_MS,
  POLL_MAX_MS,
  VIDEO_RESOLUTION_OPTIONS,
} from "./media-gen/constants";
import { groupTasksByDate, itemToTask } from "./media-gen/transforms";
import TaskCard from "./media-gen/TaskCard";
import I2VModal from "./media-gen/I2VModal";
import type { ActiveTask, MediaGenPanelProps } from "./media-gen/types";

const { Text } = Typography;

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
