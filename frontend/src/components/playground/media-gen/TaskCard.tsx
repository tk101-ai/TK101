import { Alert, Button, Card, Space, Tag, Tooltip, Typography } from "antd";
import { DownloadOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { STATUS_COLOR, STATUS_LABEL } from "./constants";
import { downloadTaskOutput } from "./transforms";
import type { ActiveTask } from "./types";

const { Text, Paragraph } = Typography;

export default function TaskCard({
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
