import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Empty, Input, Segmented, Space, Spin, Tabs, Typography, message } from "antd";
import { PictureOutlined, TeamOutlined } from "@ant-design/icons";
import {
  createVideoFromMedia,
  deleteMedia,
  getMediaModels,
  getMyMedia,
  getSharedMedia,
  mediaFileUrl,
  setMediaShared,
  type PlaygroundMediaItem,
  type PlaygroundMediaModelOption,
  type SharedMediaItem,
} from "../../api/playground";
import MediaLibraryCard from "../../components/playground/MediaLibraryCard";
import I2VModal from "../../components/playground/media-gen/I2VModal";
import type { ActiveTask } from "../../components/playground/media-gen/types";

const { Title, Paragraph } = Typography;

type KindFilter = "all" | "image" | "video";
type TabKey = "mine" | "shared";

const KIND_OPTIONS = [
  { label: "전체", value: "all" as const },
  { label: "이미지", value: "image" as const },
  { label: "영상", value: "video" as const },
];

/** 내 보관함 항목을 SharedMediaItem 형태로 승격 (카드 공용 타입). */
function asShared(item: PlaygroundMediaItem): SharedMediaItem {
  return {
    ...item,
    owner_name: null,
    owner_department: null,
    is_mine: true,
  };
}

export default function ContentLibraryPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>("mine");
  const [kind, setKind] = useState<KindFilter>("all");
  const [query, setQuery] = useState("");

  const [mine, setMine] = useState<SharedMediaItem[]>([]);
  const [shared, setShared] = useState<SharedMediaItem[]>([]);
  const [loading, setLoading] = useState(true);

  // 이미지 → 영상(i2v).
  const [videoModels, setVideoModels] = useState<PlaygroundMediaModelOption[]>([]);
  const [i2vTarget, setI2vTarget] = useState<ActiveTask | null>(null);

  useEffect(() => {
    void getMediaModels()
      .then((c) => setVideoModels(c.video))
      .catch(() => {
        /* 모델 목록 실패해도 갤러리는 동작 */
      });
  }, []);

  // 재생성/수정 — 해당 생성 탭으로 이동 + 그 항목 설정으로 폼 프리필(?reuse).
  const handleReuse = (item: SharedMediaItem) => {
    navigate(`/playground?tab=${item.media_type}&reuse=${item.id}`);
  };

  const handleConvertToVideo = (item: SharedMediaItem) => {
    setI2vTarget({
      mediaId: item.id,
      taskId: "",
      kind: "image",
      prompt: item.prompt ?? "",
      modelKey: item.model_key ?? "",
      status: "succeeded",
      outputUrl: mediaFileUrl(item.id),
      errorMessage: null,
      costUsd: null,
      sourceMediaId: null,
      createdAt: item.created_at,
    });
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
    if (!target.mediaId) return;
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
      setI2vTarget(null);
      message.info(
        "영상 생성 요청됨 (베타) — 영상 탭에서 진행 상태를 확인하세요. 텐센트 i2v 결과 수신은 점검 중입니다.",
      );
      navigate("/playground?tab=video");
    } catch (e) {
      message.error(
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          "영상 생성 시작에 실패했습니다",
      );
    }
  };

  const kindArg = kind === "all" ? undefined : kind;

  const loadMine = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await getMyMedia(kindArg, 200);
      setMine(rows.map(asShared));
    } catch {
      message.error("내 보관함을 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [kindArg]);

  const loadShared = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await getSharedMedia(kindArg, query || undefined, 120);
      setShared(rows);
    } catch {
      message.error("공유 갤러리를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, [kindArg, query]);

  useEffect(() => {
    if (tab === "mine") void loadMine();
    else void loadShared();
  }, [tab, loadMine, loadShared]);

  const handleToggleShare = useCallback(async (id: string, next: boolean) => {
    // 낙관적 업데이트 — 실패 시 롤백.
    setMine((prev) => prev.map((m) => (m.id === id ? { ...m, is_shared: next } : m)));
    try {
      await setMediaShared(id, next);
      message.success(next ? "공유했습니다" : "공유를 해제했습니다");
    } catch {
      setMine((prev) => prev.map((m) => (m.id === id ? { ...m, is_shared: !next } : m)));
      message.error(
        next ? "공유에 실패했습니다 (완료된 미디어만 공유 가능)" : "공유 해제에 실패했습니다",
      );
    }
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteMedia(id);
      setMine((prev) => prev.filter((m) => m.id !== id));
      message.success("삭제했습니다");
    } catch {
      message.error("삭제에 실패했습니다");
    }
  }, []);

  const mineGrid = useMemo(
    () => (
      <Grid
        items={mine}
        loading={loading}
        emptyText="아직 생성한 미디어가 없습니다. AI Playground에서 이미지·영상을 만들어 보세요."
        renderCard={(item) => (
          <MediaLibraryCard
            key={item.id}
            item={item}
            mode="mine"
            onToggleShare={handleToggleShare}
            onDelete={handleDelete}
            onConvertToVideo={handleConvertToVideo}
            onReuse={handleReuse}
          />
        )}
      />
    ),
    [mine, loading, handleToggleShare, handleDelete],
  );

  const sharedGrid = useMemo(
    () => (
      <Grid
        items={shared}
        loading={loading}
        emptyText="아직 공유된 미디어가 없습니다."
        renderCard={(item) => (
          <MediaLibraryCard key={item.id} item={item} mode="shared" onReuse={handleReuse} />
        )}
      />
    ),
    [shared, loading],
  );

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "8px 4px 40px" }}>
      <Title level={3} style={{ marginBottom: 2 }}>
        콘텐츠 라이브러리
      </Title>
      <Paragraph type="secondary" style={{ marginBottom: 18 }}>
        AI Playground에서 생성한 이미지·영상을 보관하고, 원하는 결과물을 다른 사용자와 공유할 수
        있습니다.
      </Paragraph>

      <Space style={{ marginBottom: 16 }} wrap>
        <Segmented options={KIND_OPTIONS} value={kind} onChange={(v) => setKind(v as KindFilter)} />
        {tab === "shared" && (
          <Input.Search
            allowClear
            placeholder="프롬프트로 검색"
            style={{ width: 260 }}
            onSearch={(v) => setQuery(v.trim())}
          />
        )}
      </Space>

      <Tabs
        activeKey={tab}
        onChange={(k) => setTab(k as TabKey)}
        items={[
          {
            key: "mine",
            label: (
              <span>
                <PictureOutlined /> 내 보관함
              </span>
            ),
            children: mineGrid,
          },
          {
            key: "shared",
            label: (
              <span>
                <TeamOutlined /> 공유 갤러리
              </span>
            ),
            children: sharedGrid,
          },
        ]}
      />

      <I2VModal
        target={i2vTarget}
        videoModels={videoModels}
        onCancel={() => setI2vTarget(null)}
        onSubmit={handleI2VSubmit}
      />
    </div>
  );
}

function Grid({
  items,
  loading,
  emptyText,
  renderCard,
}: {
  items: SharedMediaItem[];
  loading: boolean;
  emptyText: string;
  renderCard: (item: SharedMediaItem) => ReactNode;
}) {
  if (loading && items.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: "60px 0" }}>
        <Spin />
      </div>
    );
  }
  if (items.length === 0) {
    return <Empty description={emptyText} style={{ padding: "48px 0" }} />;
  }
  return <div className="media-lib-grid">{items.map(renderCard)}</div>;
}
