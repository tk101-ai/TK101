import { useCallback, useEffect, useRef, useState } from "react";
import { Empty, Input, List, message, Spin } from "antd";
import { PictureOutlined } from "@ant-design/icons";
import {
  getNasIndexStatus,
  getNasStatus,
  runNasIndex,
  searchNasText,
  type NasIndexStatus,
  type NasSearchHit,
  type NasStatus,
} from "../../api/nas";
import { useAuth } from "../../hooks/useAuth";
import NasStatusHeader from "./NasStatusHeader";
import NasResultItem from "./NasResultItem";

const POLL_INTERVAL_MS = 5000;
const SEARCH_LIMIT = 20;

type SearchPhase = "idle" | "searching" | "done";

export default function NasSearch() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [status, setStatus] = useState<NasStatus | null>(null);
  const [indexStatus, setIndexStatus] = useState<NasIndexStatus | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<NasSearchHit[]>([]);
  const [phase, setPhase] = useState<SearchPhase>("idle");
  const [runDisabled, setRunDisabled] = useState(false);

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
    fetchStatus();
    fetchIndexStatus().then((data) => {
      if (data?.running) startPolling();
    });
    return () => stopPolling();
  }, [fetchStatus, fetchIndexStatus, startPolling, stopPolling]);

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
    try {
      const res = await searchNasText(trimmed, SEARCH_LIMIT);
      setResults(res.data.results);
      setPhase("done");
    } catch {
      message.error("검색 실패");
      setPhase("done");
    }
  };

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
        style={{ marginBottom: 12 }}
      />

      <ImageSearchPlaceholder />

      <SearchResults phase={phase} results={results} />
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

interface SearchResultsProps {
  phase: SearchPhase;
  results: NasSearchHit[];
}

function SearchResults({ phase, results }: SearchResultsProps) {
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
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="검색 결과가 없습니다. 인덱싱이 완료되었는지 확인하세요."
        style={{ marginTop: 48 }}
      />
    );
  }
  return (
    <List
      itemLayout="horizontal"
      dataSource={results}
      renderItem={(hit) => <NasResultItem key={hit.id} hit={hit} />}
      style={{ marginTop: 8 }}
    />
  );
}
