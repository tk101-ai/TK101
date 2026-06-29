import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Empty, Input, Segmented, Space, Spin, Tabs, Typography, message } from "antd";
import { PictureOutlined, TeamOutlined } from "@ant-design/icons";
import {
  deleteMedia,
  getMyMedia,
  getSharedMedia,
  setMediaShared,
  type PlaygroundMediaItem,
  type SharedMediaItem,
} from "../../api/playground";
import MediaLibraryCard from "../../components/playground/MediaLibraryCard";

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
  const [tab, setTab] = useState<TabKey>("mine");
  const [kind, setKind] = useState<KindFilter>("all");
  const [query, setQuery] = useState("");

  const [mine, setMine] = useState<SharedMediaItem[]>([]);
  const [shared, setShared] = useState<SharedMediaItem[]>([]);
  const [loading, setLoading] = useState(true);

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
        renderCard={(item) => <MediaLibraryCard key={item.id} item={item} mode="shared" />}
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
