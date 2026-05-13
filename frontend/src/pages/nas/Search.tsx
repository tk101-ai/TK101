import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, Button, Empty, Input, List, Radio, Space, Spin, Tag, message } from "antd";
import type { RadioChangeEvent } from "antd";
import { PictureOutlined } from "@ant-design/icons";
import {
  getNasIndexStatus,
  getNasStatus,
  getNasTopFolders,
  runNasIndex,
  searchNasText,
  type NasIndexStatus,
  type NasSearchHit,
  type NasSearchParams,
  type NasStatus,
} from "../../api/nas";
import { useAuth } from "../../hooks/useAuth";
import { fileIconType } from "./nasUtils";
import NasStatusHeader from "./NasStatusHeader";
import NasResultItem from "./NasResultItem";
import NasFilterBar, {
  periodToMtimeFrom,
  type NasFilterValue,
} from "./NasFilterBar";

const POLL_INTERVAL_MS = 5000;
// 검색 결과 페이지 크기. 백엔드 NasSearchRequest.limit 상한이 50이므로 그 안에서 단계적으로 늘린다.
const SEARCH_PAGE_SIZE = 20;
const SEARCH_LIMIT_MAX = 50;

type SearchSort = "score" | "recent" | "name";

const SORT_OPTIONS: { key: SearchSort; label: string }[] = [
  { key: "score", label: "점수순" },
  { key: "recent", label: "최신순" },
  { key: "name", label: "파일명순" },
];

const DEFAULT_FILTER: NasFilterValue = {
  fileKinds: [],
  pathPrefix: null,
  period: "all",
};

type SearchPhase = "idle" | "searching" | "done";

export default function NasSearch() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [status, setStatus] = useState<NasStatus | null>(null);
  const [indexStatus, setIndexStatus] = useState<NasIndexStatus | null>(null);
  const [query, setQuery] = useState("");
  // submittedQuery는 실제 검색에 사용된 마지막 쿼리. 하이라이트/페이지네이션에 재사용.
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [results, setResults] = useState<NasSearchHit[]>([]);
  const [phase, setPhase] = useState<SearchPhase>("idle");
  const [limit, setLimit] = useState<number>(SEARCH_PAGE_SIZE);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sort, setSort] = useState<SearchSort>("score");
  const [runDisabled, setRunDisabled] = useState(false);
  const [folders, setFolders] = useState<string[]>([]);
  const [filter, setFilter] = useState<NasFilterValue>(DEFAULT_FILTER);

  const pollRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await getNasStatus();
      setStatus(res.data);
    } catch {
      message.error("NAS 상태 조회 실패");
    }
  }, []);

  const fetchIndexStatus = useCallback(async () => {
    try {
      const res = await getNasIndexStatus();
      setIndexStatus(res.data);
      return res.data;
    } catch {
      return null;
    }
  }, []);

  const fetchTopFolders = useCallback(async () => {
    try {
      const res = await getNasTopFolders();
      setFolders(res.data.folders);
    } catch {
      // 폴더 목록 조회 실패는 무시 — 검색은 계속 동작해야 함
      setFolders([]);
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = window.setInterval(async () => {
      const data = await fetchIndexStatus();
      if (data && !data.running) {
        stopPolling();
        fetchStatus();
        if (data.last_error) {
          message.warning(`인덱싱 종료 (오류 발생: ${data.errors}건)`);
        } else {
          message.success("인덱싱 완료");
        }
      }
    }, POLL_INTERVAL_MS);
  }, [fetchIndexStatus, fetchStatus, stopPolling]);

  useEffect(() => {
    // 마운트 시 NAS 상태/인덱스/폴더 fetch + 실행 중이면 폴링 시작 (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchStatus();
    void fetchTopFolders();
    void fetchIndexStatus().then((data) => {
      if (data?.running) startPolling();
    });
    return () => stopPolling();
  }, [fetchStatus, fetchIndexStatus, fetchTopFolders, startPolling, stopPolling]);

  const buildSearchParams = useCallback(
    (q: string, lim: number): NasSearchParams => {
      const params: NasSearchParams = { query: q, limit: lim };
      if (filter.fileKinds.length > 0) {
        params.file_kinds = filter.fileKinds;
      }
      if (filter.pathPrefix) {
        params.path_prefix = filter.pathPrefix;
      }
      const mtimeFrom = periodToMtimeFrom(filter.period);
      if (mtimeFrom) {
        params.mtime_from = mtimeFrom;
      }
      return params;
    },
    [filter],
  );

  const handleRunIndex = async () => {
    setRunDisabled(true);
    try {
      await runNasIndex();
      message.success("인덱싱이 시작되었습니다");
      await fetchIndexStatus();
      startPolling();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status === 409) {
        message.warning("이미 인덱싱이 진행 중입니다");
        await fetchIndexStatus();
        startPolling();
      } else if (status === 403) {
        message.error("권한이 없습니다");
      } else {
        message.error("인덱싱 시작 실패");
      }
    } finally {
      setRunDisabled(false);
    }
  };

  const handleSearch = async (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      message.info("검색어를 입력하세요");
      return;
    }
    setPhase("searching");
    setLimit(SEARCH_PAGE_SIZE);
    try {
      const res = await searchNasText(buildSearchParams(trimmed, SEARCH_PAGE_SIZE));
      setResults(res.data.results);
      setSubmittedQuery(trimmed);
      setPhase("done");
    } catch {
      message.error("검색 실패");
      setPhase("done");
    }
  };

  const handleLoadMore = async () => {
    if (loadingMore || !submittedQuery) return;
    const nextLimit = Math.min(limit + SEARCH_PAGE_SIZE, SEARCH_LIMIT_MAX);
    if (nextLimit <= limit) return;
    setLoadingMore(true);
    try {
      const res = await searchNasText(buildSearchParams(submittedQuery, nextLimit));
      setResults(res.data.results);
      setLimit(nextLimit);
    } catch {
      message.error("추가 결과 조회 실패");
    } finally {
      setLoadingMore(false);
    }
  };

  // 정렬은 클라이언트에서. 백엔드 응답은 점수순으로 이미 정렬되어 있음.
  const sortedResults = useMemo(() => {
    if (sort === "score") return results;
    const copy = [...results];
    if (sort === "recent") {
      copy.sort((a, b) => {
        const ta = a.mtime ? Date.parse(a.mtime) : 0;
        const tb = b.mtime ? Date.parse(b.mtime) : 0;
        return tb - ta;
      });
    } else if (sort === "name") {
      copy.sort((a, b) => (a.name || "").localeCompare(b.name || "", "ko"));
    }
    return copy;
  }, [results, sort]);

  const canLoadMore =
    phase === "done" && results.length >= limit && limit < SEARCH_LIMIT_MAX;

  return (
    <div style={{ maxWidth: 1100 }}>
      <NasStatusHeader
        status={status}
        indexStatus={indexStatus}
        isAdmin={isAdmin}
        onRunIndex={handleRunIndex}
        runDisabled={runDisabled}
      />

      <Input.Search
        size="large"
        allowClear
        enterButton="검색"
        placeholder="검색어를 입력하세요 (예: 정량 평가서 양식)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onSearch={handleSearch}
        loading={phase === "searching"}
        style={{ marginBottom: 8 }}
      />

      <NasFilterBar value={filter} onChange={setFilter} folders={folders} />

      <ImageSearchPlaceholder />

      {phase === "done" && results.length > 0 && (
        <ResultSummaryBar
          results={results}
          totalShown={sortedResults.length}
          sort={sort}
          onSortChange={setSort}
        />
      )}

      <SearchResults
        phase={phase}
        results={sortedResults}
        query={submittedQuery}
        canLoadMore={canLoadMore}
        loadingMore={loadingMore}
        onLoadMore={handleLoadMore}
      />
    </div>
  );
}

function ImageSearchPlaceholder() {
  return (
    <div
      style={{
        border: "1px dashed #d9d9d9",
        borderRadius: 6,
        padding: "14px 16px",
        marginBottom: 24,
        background: "#fafafa",
        color: "#bfbfbf",
        display: "flex",
        alignItems: "center",
        gap: 10,
        fontSize: 13,
      }}
    >
      <PictureOutlined style={{ fontSize: 18 }} />
      <span>이미지로 검색 (v0.6.1 출시 예정)</span>
    </div>
  );
}

interface MimeBucket {
  key: string;
  label: string;
  count: number;
  color: string;
}

const KIND_LABELS: Record<string, { label: string; color: string }> = {
  pdf: { label: "PDF", color: "red" },
  doc: { label: "Word", color: "blue" },
  ppt: { label: "PPT", color: "volcano" },
  xls: { label: "엑셀", color: "green" },
  hwp: { label: "한글", color: "geekblue" },
  image: { label: "이미지", color: "purple" },
  file: { label: "기타", color: "default" },
};

function summarizeMime(results: NasSearchHit[]): MimeBucket[] {
  const counts = new Map<string, number>();
  for (const hit of results) {
    const kind = fileIconType(hit.mime_type, hit.file_type);
    counts.set(kind, (counts.get(kind) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .map(([key, count]) => ({
      key,
      label: KIND_LABELS[key]?.label ?? key,
      color: KIND_LABELS[key]?.color ?? "default",
      count,
    }))
    .sort((a, b) => b.count - a.count);
}

interface ResultSummaryBarProps {
  results: NasSearchHit[];
  totalShown: number;
  sort: SearchSort;
  onSortChange: (next: SearchSort) => void;
}

function ResultSummaryBar({ results, totalShown, sort, onSortChange }: ResultSummaryBarProps) {
  const buckets = useMemo(() => summarizeMime(results), [results]);

  const handleChange = (e: RadioChangeEvent) => {
    onSortChange(e.target.value as SearchSort);
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 16,
        flexWrap: "wrap",
        marginTop: 4,
        marginBottom: 12,
        padding: "8px 12px",
        background: "#fafafa",
        border: "1px solid #f0f0f0",
        borderRadius: 6,
      }}
    >
      <Space size={8} wrap>
        <span style={{ fontSize: 13, color: "#595959", fontWeight: 600 }}>
          {totalShown}건
        </span>
        <span style={{ color: "#d9d9d9" }}>·</span>
        {buckets.map((b) => (
          <Tag key={b.key} color={b.color} style={{ marginRight: 0 }}>
            {b.label} {b.count}
          </Tag>
        ))}
      </Space>
      <Radio.Group value={sort} onChange={handleChange} size="small" optionType="button">
        {SORT_OPTIONS.map((opt) => (
          <Radio.Button key={opt.key} value={opt.key}>
            {opt.label}
          </Radio.Button>
        ))}
      </Radio.Group>
    </div>
  );
}

interface SearchResultsProps {
  phase: SearchPhase;
  results: NasSearchHit[];
  query: string;
  canLoadMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

function SearchResults({
  phase,
  results,
  query,
  canLoadMore,
  loadingMore,
  onLoadMore,
}: SearchResultsProps) {
  if (phase === "idle") {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="검색어를 입력하세요"
        style={{ marginTop: 48 }}
      />
    );
  }
  if (phase === "searching") {
    return (
      <div style={{ textAlign: "center", marginTop: 48 }}>
        <Spin tip="검색 중..." />
      </div>
    );
  }
  if (results.length === 0) {
    return <EmptySearchHelp />;
  }
  return (
    <>
      <List
        itemLayout="horizontal"
        dataSource={results}
        renderItem={(hit) => <NasResultItem key={hit.id} hit={hit} highlight={query} />}
        style={{ marginTop: 8 }}
      />
      {canLoadMore && (
        <div style={{ textAlign: "center", margin: "16px 0 32px" }}>
          <Button onClick={onLoadMore} loading={loadingMore}>
            더 보기
          </Button>
        </div>
      )}
      {!canLoadMore && results.length >= SEARCH_LIMIT_MAX && (
        <div
          style={{
            textAlign: "center",
            margin: "16px 0 32px",
            color: "#bfbfbf",
            fontSize: 12,
          }}
        >
          최대 {SEARCH_LIMIT_MAX}건까지 표시됩니다. 검색어나 필터를 조정해보세요.
        </div>
      )}
    </>
  );
}

function EmptySearchHelp() {
  return (
    <div style={{ marginTop: 32 }}>
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span style={{ color: "#595959" }}>검색 결과가 없습니다</span>
        }
      />
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 16, maxWidth: 720, marginLeft: "auto", marginRight: "auto" }}
        message="검색 팁"
        description={
          <ul style={{ margin: "4px 0 0 18px", padding: 0, fontSize: 13, lineHeight: 1.8 }}>
            <li>한글/영어를 함께 시도해보세요 (예: "정량 평가서" / "evaluation form")</li>
            <li>파일명 일부 키워드로도 검색 가능합니다</li>
            <li>유사 단어/동의어를 시도해보세요 (예: "제안서" → "기획안", "RFP")</li>
            <li>형식·폴더·기간 필터를 풀고 다시 검색해보세요</li>
            <li>인덱싱이 진행 중이면 일부 자료는 아직 검색에 반영되지 않을 수 있습니다</li>
          </ul>
        }
      />
    </div>
  );
}
