import { useState } from "react";
import { Avatar, Button, Popconfirm, Switch, Tag, Tooltip, Typography, message } from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  HighlightOutlined,
  RedoOutlined,
  ShareAltOutlined,
  UserOutlined,
  VideoCameraOutlined,
} from "@ant-design/icons";
import { downloadMedia, mediaFileUrl, type SharedMediaItem } from "../../api/playground";

const { Text, Paragraph } = Typography;

type Mode = "mine" | "shared";

interface MediaLibraryCardProps {
  item: SharedMediaItem;
  mode: Mode;
  /** 공유 토글 (mine 모드). 낙관적 업데이트 후 실패 시 호출자가 롤백. */
  onToggleShare?: (id: string, next: boolean) => Promise<void>;
  /** 삭제 (mine 모드). */
  onDelete?: (id: string) => Promise<void>;
  /** 이미지 → 영상(i2v). 본인 이미지에서만 노출. */
  onConvertToVideo?: (item: SharedMediaItem) => void;
  /** 이 항목 설정으로 생성 폼을 채워 재생성/수정. */
  onReuse?: (item: SharedMediaItem) => void;
  /** 이 이미지를 베이스로 리터치/편집(i2i). 본인 이미지에서만 노출. */
  onRetouch?: (item: SharedMediaItem) => void;
  /** 이 영상을 베이스로 리터치(v2v). 본인 영상에서만 노출. */
  onRetouchVideo?: (item: SharedMediaItem) => void;
}

function formatDate(iso: string): string {
  // YYYY-MM-DD HH:mm (로컬). 라이브러리 카드용 짧은 표기.
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

export default function MediaLibraryCard({
  item,
  mode,
  onToggleShare,
  onDelete,
  onConvertToVideo,
  onReuse,
  onRetouch,
  onRetouchVideo,
}: MediaLibraryCardProps) {
  const [busy, setBusy] = useState(false);
  const isVideo = item.media_type === "video";
  const src = mediaFileUrl(item.id);

  const handleDownload = async () => {
    setBusy(true);
    try {
      await downloadMedia(item);
    } catch {
      message.error("다운로드에 실패했습니다");
    } finally {
      setBusy(false);
    }
  };

  const handleToggle = async (next: boolean) => {
    if (!onToggleShare) return;
    setBusy(true);
    try {
      await onToggleShare(item.id, next);
    } finally {
      setBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!onDelete) return;
    setBusy(true);
    try {
      await onDelete(item.id);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="media-lib-card">
      <div className="media-lib-card__thumb">
        {isVideo ? (
          <video src={src} controls preload="metadata" />
        ) : (
          <img src={src} alt={item.prompt ?? "생성 이미지"} loading="lazy" />
        )}
        <span className="media-lib-card__kind">{isVideo ? "VIDEO" : "IMAGE"}</span>
        {mode === "mine" && item.is_shared && (
          <span className="media-lib-card__shared-badge">
            <ShareAltOutlined /> 공유 중
          </span>
        )}
      </div>

      <div className="media-lib-card__body">
        <Paragraph
          className="media-lib-card__prompt"
          ellipsis={{ rows: 2, tooltip: item.prompt ?? undefined }}
        >
          {item.prompt || <Text type="secondary">(프롬프트 없음)</Text>}
        </Paragraph>

        <div className="media-lib-card__meta">
          {item.model_key && (
            <Tag bordered={false} color="geekblue">
              {item.model_key}
            </Tag>
          )}
          <Text type="secondary" style={{ fontSize: 12 }}>
            {formatDate(item.created_at)}
          </Text>
        </div>

        {mode === "shared" && (
          <div className="media-lib-card__owner">
            <Avatar size={20} icon={<UserOutlined />} />
            <Text style={{ fontSize: 12 }}>{item.owner_name ?? "알 수 없음"}</Text>
            {item.owner_department && (
              <Tag bordered={false} style={{ fontSize: 11 }}>
                {item.owner_department}
              </Tag>
            )}
            {item.is_mine && (
              <Tag bordered={false} color="green" style={{ fontSize: 11 }}>
                내 미디어
              </Tag>
            )}
          </div>
        )}

        <div className="media-lib-card__actions">
          <Button size="small" icon={<DownloadOutlined />} onClick={handleDownload} loading={busy}>
            다운로드
          </Button>

          {!isVideo && onRetouch && (
            <Tooltip title="이 이미지를 베이스로 수정/리터치 (image-to-image)">
              <Button
                size="small"
                type="primary"
                icon={<HighlightOutlined />}
                onClick={() => onRetouch(item)}
              >
                리터치
              </Button>
            </Tooltip>
          )}

          {isVideo && onRetouchVideo && (
            <Tooltip title="이 영상을 베이스로 수정/리터치 (video-to-video · 최근 생성분)">
              <Button
                size="small"
                type="primary"
                icon={<HighlightOutlined />}
                onClick={() => onRetouchVideo(item)}
              >
                영상 리터치
              </Button>
            </Tooltip>
          )}

          {!isVideo && onConvertToVideo && (
            <Tooltip title="이 이미지로 영상을 만듭니다 (image-to-video · 베타)">
              <Button
                size="small"
                icon={<VideoCameraOutlined />}
                onClick={() => onConvertToVideo(item)}
              >
                영상화
              </Button>
            </Tooltip>
          )}

          {onReuse && (
            <Tooltip title="이 설정(프롬프트·모델)으로 재생성/수정">
              <Button size="small" icon={<RedoOutlined />} onClick={() => onReuse(item)}>
                재생성
              </Button>
            </Tooltip>
          )}

          {mode === "mine" && onToggleShare && (
            <Tooltip
              title={
                item.is_shared
                  ? "공유 해제 — 다른 사용자에게 더 이상 노출되지 않습니다"
                  : "공유 — 공유 갤러리에서 모든 사용자가 보고 사용할 수 있습니다"
              }
            >
              <span className="media-lib-card__share-toggle">
                <ShareAltOutlined />
                <Switch
                  size="small"
                  checked={item.is_shared}
                  loading={busy}
                  onChange={handleToggle}
                />
              </span>
            </Tooltip>
          )}

          {mode === "mine" && onDelete && (
            <Popconfirm
              title="이 미디어를 삭제할까요?"
              description="복구할 수 없습니다."
              okText="삭제"
              okButtonProps={{ danger: true }}
              cancelText="취소"
              onConfirm={handleDelete}
            >
              <Button size="small" danger icon={<DeleteOutlined />} loading={busy}>
                삭제
              </Button>
            </Popconfirm>
          )}
        </div>
      </div>
    </div>
  );
}
