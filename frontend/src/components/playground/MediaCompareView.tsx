import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { ClearOutlined, SendOutlined } from "@ant-design/icons";
import {
  QUOTA_EXCEEDED_MESSAGE,
  createImageTask,
  createVideoTask,
  describeTask,
  getMediaModels,
  isQuotaExceededError,
  type PlaygroundMediaModelOption,
  type PlaygroundTaskStatus,
} from "../../api/playground";

const { Text, Paragraph } = Typography;

type MediaKind = "image" | "video";

interface MediaCompareViewProps {
  kind: MediaKind;
}

interface Lane {
  modelKey: string;
  modelLabel: string;
  taskId: string | null;
  status: PlaygroundTaskStatus["status"];
  outputUrl: string | null;
  errorMessage: string | null;
}

const STATUS_COLOR: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "default",
  running: "processing",
  succeeded: "success",
  failed: "error",
  unknown: "warning",
};

const STATUS_LABEL: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "대기",
  running: "생성 중",
  succeeded: "완료",
  failed: "실패",
  unknown: "?",
};

const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MS = 5 * 60 * 1000;

/**
 * 이미지/영상 동시 비교 패널 (사용자 요구 #5).
 *
 * - N개 모델 체크 → 같은 프롬프트로 동시 task 생성 → 결과 grid.
 * - 비용 N배 안내. 의식적 사용.
 * - 이미지: aspect_ratio 1:1 고정. 영상: 5초 720P 16:9 고정 (단순화).
 *   더 세밀한 옵션은 단일 모드 (MediaGenPanel) 사용.
 */
export default function MediaCompareView({ kind }: MediaCompareViewProps) {
  const [models, setModels] = useState<PlaygroundMediaModelOption[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [lanes, setLanes] = useState<Lane[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const pollersRef = useRef<Map<string, ReturnType<typeof setInterval>>>(new Map());

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getMediaModels();
        if (cancelled) return;
        setModels(kind === "image" ? data.image : data.video);
      } catch {
        // 빈 목록 유지.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [kind]);

  useEffect(() => {
    return () => {
      for (const id of pollersRef.current.values()) clearInterval(id);
      pollersRef.current.clear();
    };
  }, []);

  const toggleModel = (key: string, checked: boolean) =>
    setSelected((prev) => (checked ? [...prev, key] : prev.filter((x) => x !== key)));

  const startPolling = (taskId: string) => {
    const startedAt = Date.now();
    const poll = async () => {
      try {
        const status = await describeTask(kind, taskId);
        setLanes((prev) =>
          prev.map((l) =>
            l.taskId === taskId
              ? {
                  ...l,
                  status: status.status,
                  outputUrl: status.output_url,
                  errorMessage: status.error_message,
                }
              : l,
          ),
        );
        if (status.status === "succeeded" || status.status === "failed") {
          const id = pollersRef.current.get(taskId);
          if (id) clearInterval(id);
          pollersRef.current.delete(taskId);
        }
      } catch (err: unknown) {
        if (Date.now() - startedAt > POLL_MAX_MS) {
          const id = pollersRef.current.get(taskId);
          if (id) clearInterval(id);
          pollersRef.current.delete(taskId);
          setLanes((prev) =>
            prev.map((l) =>
              l.taskId === taskId
                ? {
                    ...l,
                    status: "failed",
                    errorMessage:
                      err instanceof Error ? err.message : "폴링 타임아웃",
                  }
                : l,
            ),
          );
        }
      }
    };
    void poll();
    const handle = setInterval(poll, POLL_INTERVAL_MS);
    pollersRef.current.set(taskId, handle);
  };

  const onSubmit = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    if (selected.length === 0) {
      message.warning("모델을 1개 이상 선택해주세요");
      return;
    }
    if (submitting) return;
    setSubmitting(true);

    const selectedMeta = selected
      .map((k) => models.find((m) => m.key === k))
      .filter((x): x is PlaygroundMediaModelOption => !!x);

    const initialLanes: Lane[] = selectedMeta.map((m) => ({
      modelKey: m.key,
      modelLabel: m.label,
      taskId: null,
      status: "pending",
      outputUrl: null,
      errorMessage: null,
    }));
    setLanes(initialLanes);

    // 병렬 task 생성.
    const results = await Promise.allSettled(
      selectedMeta.map((m) =>
        kind === "image"
          ? createImageTask({
              prompt: trimmed,
              model_key: m.key,
              aspect_ratio: "1:1",
              enhance_prompt: true,
            })
          : createVideoTask({
              prompt: trimmed,
              model_key: m.key,
              duration: 5,
              resolution: "720P",
              aspect_ratio: "16:9",
              enhance_prompt: true,
            }),
      ),
    );

    setLanes((prev) =>
      prev.map((lane, i) => {
        const r = results[i];
        if (r.status === "fulfilled") {
          return { ...lane, taskId: r.value.task_id, status: "running" };
        }
        const errMsg = isQuotaExceededError(r.reason)
          ? QUOTA_EXCEEDED_MESSAGE
          : r.reason instanceof Error
            ? r.reason.message
            : "task 생성 실패";
        return {
          ...lane,
          status: "failed",
          errorMessage: errMsg,
        };
      }),
    );

    // 한도 초과가 1건이라도 있으면 토스트.
    const anyQuotaErr = results.some(
      (r) => r.status === "rejected" && isQuotaExceededError(r.reason),
    );
    if (anyQuotaErr) {
      message.error(QUOTA_EXCEEDED_MESSAGE);
    }

    // 폴링 등록.
    for (const r of results) {
      if (r.status === "fulfilled") startPolling(r.value.task_id);
    }

    setSubmitting(false);
  };

  const reset = () => {
    for (const id of pollersRef.current.values()) clearInterval(id);
    pollersRef.current.clear();
    setLanes([]);
  };

  return (
    <div>
      <Card size="small" style={{ marginBottom: 12 }}>
        <Text strong style={{ fontSize: 12 }}>
          {kind === "image" ? "이미지" : "영상"} 모델 ({selected.length}개 선택)
        </Text>
        <div style={{ marginTop: 8 }}>
          <Space wrap>
            {models.map((m) => (
              <Checkbox
                key={m.key}
                checked={selected.includes(m.key)}
                onChange={(e) => toggleModel(m.key, e.target.checked)}
              >
                {m.label}
                {m.badge && (
                  <Tag style={{ marginLeft: 4 }} color="blue">
                    {m.badge}
                  </Tag>
                )}
              </Checkbox>
            ))}
          </Space>
        </div>
      </Card>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Input.TextArea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder={
            kind === "image"
              ? "예: A clean product-style capybara mascot"
              : "예: A capybara mascot moves in a 5s studio video"
          }
          autoSize={{ minRows: 2, maxRows: 5 }}
          disabled={submitting}
        />
        <div
          style={{
            marginTop: 8,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <Text type="warning" style={{ fontSize: 11 }}>
            선택 모델 수만큼 비용 발생 ({selected.length} × {kind === "image" ? "장당" : "초당"})
          </Text>
          <Space>
            <Button icon={<ClearOutlined />} onClick={reset} disabled={submitting}>
              초기화
            </Button>
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={onSubmit}
              loading={submitting}
            >
              동시 생성
            </Button>
          </Space>
        </div>
      </Card>

      {lanes.length === 0 ? (
        <Alert
          type="info"
          showIcon
          message={`선택한 모델에 ${kind === "image" ? "이미지" : "영상"} 동시 생성 결과가 컬럼별로 표시됩니다`}
        />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(lanes.length, 4)}, minmax(0, 1fr))`,
            gap: 12,
          }}
        >
          {lanes.map((l) => (
            <Card
              key={l.modelKey}
              size="small"
              title={
                <Space>
                  <Tag color={STATUS_COLOR[l.status]}>{STATUS_LABEL[l.status]}</Tag>
                  <Text code style={{ fontSize: 11 }}>
                    {l.modelLabel}
                  </Text>
                </Space>
              }
            >
              {l.status === "succeeded" && l.outputUrl ? (
                kind === "image" ? (
                  <img
                    src={l.outputUrl}
                    alt={l.modelLabel}
                    style={{ width: "100%", borderRadius: 4 }}
                  />
                ) : (
                  <video
                    src={l.outputUrl}
                    controls
                    style={{ width: "100%", borderRadius: 4 }}
                  />
                )
              ) : l.status === "failed" ? (
                <Alert
                  type="error"
                  showIcon
                  message="실패"
                  description={l.errorMessage ?? "원인 미상"}
                />
              ) : (
                <Paragraph style={{ fontSize: 12, color: "rgba(0,0,0,0.45)", margin: 0 }}>
                  {l.status === "pending" ? "대기 중…" : "생성 중…"}
                </Paragraph>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
