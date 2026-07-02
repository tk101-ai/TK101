import { useState } from "react";
import { Alert, Button, Image, Input, Space, Tag, Tooltip, Typography } from "antd";
import {
  DownloadOutlined,
  HighlightOutlined,
  PictureOutlined,
  PlayCircleOutlined,
  RedoOutlined,
  SendOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { mediaFileUrl } from "../../../api/playground";
import { STATUS_COLOR, STATUS_LABEL } from "./constants";
import { downloadTaskOutput } from "./transforms";
import type { ActiveTask } from "./types";

const { Text, Paragraph } = Typography;

/** 갤러리용 컴팩트 카드 — 썸네일(클릭 시 확대) + 짧은 메타. 참고 원본(이미지/영상) 표시. */
export default function TaskCard({
  task,
  onConvertToVideo,
  onReuse,
  onRetouch,
  onRetouchVideo,
  onFollowUp,
}: {
  task: ActiveTask;
  onConvertToVideo?: () => void;
  /** 이 항목의 설정으로 폼을 채워 이어서 재생성/수정. */
  onReuse?: () => void;
  /** 이 이미지를 베이스로 리터치/편집(i2i). */
  onRetouch?: () => void;
  /** 이 영상을 베이스로 리터치(v2v). */
  onRetouchVideo?: () => void;
  /** 이 결과를 베이스로 카드에서 바로 후속 프롬프트 실행(영상=v2v / 이미지=i2i). */
  onFollowUp?: (prompt: string) => void;
}) {
  const [followPrompt, setFollowPrompt] = useState("");
  const [followBusy, setFollowBusy] = useState(false);
  const canEditImage =
    task.kind === "image" && task.status === "succeeded" && Boolean(task.mediaId);
  const canEditVideo =
    task.kind === "video" && task.status === "succeeded" && Boolean(task.mediaId);
  const canConvert = Boolean(onConvertToVideo) && canEditImage;
  const succeeded = task.status === "succeeded" && Boolean(task.outputUrl);
  const canFollowUp = Boolean(onFollowUp) && (canEditImage || canEditVideo);
  const sourceIsVideo = task.sourceMediaKind === "video";

  const submitFollowUp = () => {
    const trimmed = followPrompt.trim();
    if (!trimmed || !onFollowUp) return;
    setFollowBusy(true);
    try {
      onFollowUp(trimmed);
      setFollowPrompt("");
    } finally {
      setFollowBusy(false);
    }
  };

  return (
    <div
      style={{
        border: "1px solid rgba(0,0,0,0.08)",
        borderRadius: 12,
        overflow: "hidden",
        background: "#fff",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <div
        style={{
          position: "relative",
          aspectRatio: "1 / 1",
          background: "#f4f5f7",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {succeeded ? (
          task.kind === "image" ? (
            <Image
              src={task.outputUrl!}
              alt={task.prompt}
              width="100%"
              height="100%"
              style={{ objectFit: "cover" }}
              preview={{ mask: "크게 보기" }}
            />
          ) : (
            <video
              src={task.outputUrl!}
              controls
              preload="metadata"
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
          )
        ) : task.status === "failed" ? (
          <Text type="danger" style={{ fontSize: 12 }}>
            생성 실패
          </Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            처리 중…
          </Text>
        )}

        <span style={{ position: "absolute", top: 6, left: 6 }}>
          <Tag color={STATUS_COLOR[task.status]} style={{ margin: 0, fontSize: 10 }}>
            {STATUS_LABEL[task.status]}
          </Tag>
        </span>

        {/* 참고(소스) 원본 — 우하단 작은 썸네일. 원본이 영상이면 video, 이미지면 img. */}
        {task.sourceMediaId && (
          <Tooltip
            title={
              sourceIsVideo
                ? "이 영상을 리터치해 만든 결과 (참고 원본)"
                : "이 이미지로 만든 결과 (참고 원본)"
            }
          >
            <div
              style={{
                position: "absolute",
                bottom: 6,
                right: 6,
                width: 40,
                height: 40,
                borderRadius: 6,
                overflow: "hidden",
                border: "2px solid #fff",
                boxShadow: "0 1px 4px rgba(0,0,0,0.25)",
                background: "#fff",
              }}
            >
              {sourceIsVideo ? (
                <video
                  src={mediaFileUrl(task.sourceMediaId)}
                  muted
                  preload="metadata"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <img
                  src={mediaFileUrl(task.sourceMediaId)}
                  alt="참고 원본"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              )}
              {sourceIsVideo ? (
                <VideoCameraOutlined
                  style={{
                    position: "absolute",
                    top: 1,
                    left: 1,
                    fontSize: 9,
                    color: "#fff",
                    textShadow: "0 0 2px rgba(0,0,0,0.6)",
                  }}
                />
              ) : (
                <PictureOutlined
                  style={{
                    position: "absolute",
                    top: 1,
                    left: 1,
                    fontSize: 9,
                    color: "#fff",
                    textShadow: "0 0 2px rgba(0,0,0,0.6)",
                  }}
                />
              )}
            </div>
          </Tooltip>
        )}
      </div>

      <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6 }}>
        <Paragraph
          ellipsis={{
            rows: 2,
            expandable: true,
            symbol: "자세히",
          }}
          style={{ margin: 0, fontSize: 12, minHeight: 32 }}
          type="secondary"
        >
          {task.prompt || "(프롬프트 없음)"}
        </Paragraph>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          {task.modelKey && (
            <Text code style={{ fontSize: 10 }}>
              {task.modelKey}
            </Text>
          )}
          {task.costUsd != null && (
            <Text type="secondary" style={{ fontSize: 10 }}>
              ${Number(task.costUsd).toFixed(3)}
            </Text>
          )}
          <span style={{ flex: 1 }} />
          {onRetouch && canEditImage && (
            <Tooltip title="이 이미지를 베이스로 리터치/수정">
              <Button size="small" type="text" icon={<HighlightOutlined />} onClick={onRetouch} />
            </Tooltip>
          )}
          {onRetouchVideo && canEditVideo && (
            <Tooltip title="이 영상을 베이스로 리터치/수정 (최근 생성분)">
              <Button
                size="small"
                type="text"
                icon={<HighlightOutlined />}
                onClick={onRetouchVideo}
              />
            </Tooltip>
          )}
          {onReuse && (
            <Tooltip title="이 설정으로 재생성/수정">
              <Button size="small" type="text" icon={<RedoOutlined />} onClick={onReuse} />
            </Tooltip>
          )}
          {succeeded && (
            <Tooltip title="다운로드">
              <Button
                size="small"
                type="text"
                icon={<DownloadOutlined />}
                onClick={() => downloadTaskOutput(task)}
              />
            </Tooltip>
          )}
          {canConvert && (
            <Tooltip title="이 이미지로 영상 만들기">
              <Button
                size="small"
                type="text"
                icon={<PlayCircleOutlined />}
                onClick={onConvertToVideo}
              />
            </Tooltip>
          )}
        </div>
        {task.status === "failed" && task.errorMessage && (
          <Alert
            type="error"
            showIcon
            message={task.errorMessage}
            style={{ fontSize: 11, padding: "4px 8px" }}
          />
        )}

        {/* 이어서 편집 — 이 결과를 베이스로 후속 프롬프트를 바로 실행(영상=v2v/이미지=i2i) */}
        {canFollowUp && (
          <Space.Compact style={{ width: "100%" }}>
            <Input
              size="small"
              value={followPrompt}
              onChange={(e) => setFollowPrompt(e.target.value)}
              onPressEnter={submitFollowUp}
              placeholder={
                task.kind === "video"
                  ? "이어서 수정 (예: 배경만 낮으로)"
                  : "이어서 수정 (예: 색감을 따뜻하게)"
              }
              style={{ fontSize: 12 }}
            />
            <Tooltip title="이 결과를 베이스로 이어서 편집">
              <Button
                size="small"
                type="primary"
                icon={<SendOutlined />}
                loading={followBusy}
                disabled={!followPrompt.trim()}
                onClick={submitFollowUp}
              />
            </Tooltip>
          </Space.Compact>
        )}
      </div>
    </div>
  );
}
