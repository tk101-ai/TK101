import { useCallback, useEffect, useMemo, useState } from "react";
import dayjs from "dayjs";
import { message } from "antd";
import api from "../../../api/client";
import { listTrend, refreshAll, type TrendPoint } from "../../../api/sns";
import {
  aggregateByPlatform,
  buildTotalRow,
  computeTotals,
  deriveWeekNumbers,
  pivotWeeklyRows,
} from "./channelTransforms";
import type { GrowthCard, TopPost, WeeklyKpiRow } from "./types";

export function useMarketing1Data() {
  const [year, setYear] = useState<number>(dayjs().year());
  const [month, setMonth] = useState<number>(dayjs().month() + 1);

  const [weeklyData, setWeeklyData] = useState<WeeklyKpiRow[]>([]);
  const [growthData, setGrowthData] = useState<GrowthCard[]>([]);
  const [topPosts, setTopPosts] = useState<TopPost[]>([]);
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);

  const [topLanguage, setTopLanguage] = useState<string>("all");
  const [topPlatform, setTopPlatform] = useState<string>("all");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const topParams: Record<string, string | number> = { limit: 5 };
      if (topLanguage !== "all") topParams.language = topLanguage;
      if (topPlatform !== "all") topParams.platform = topPlatform;

      // 위젯별 독립 fetch: 한 엔드포인트가 실패해도 나머지는 그대로 표시한다
      // (예전엔 Promise.all 이라 trend 한 건 실패가 전체 대시보드를 비웠음).
      const [weeklyR, growthR, topR, trendR] = await Promise.allSettled([
        api.get<WeeklyKpiRow[]>("/api/sns/stats/weekly", {
          params: { year, month },
        }),
        api.get<GrowthCard[]>("/api/sns/stats/growth"),
        api.get<TopPost[]>("/api/sns/stats/top-posts", { params: topParams }),
        listTrend({ months: 6 }),
      ]);
      setWeeklyData(weeklyR.status === "fulfilled" ? (weeklyR.value.data ?? []) : []);
      setGrowthData(growthR.status === "fulfilled" ? (growthR.value.data ?? []) : []);
      setTopPosts(topR.status === "fulfilled" ? (topR.value.data ?? []) : []);
      setTrendData(trendR.status === "fulfilled" ? (trendR.value.data ?? []) : []);

      const failed = [weeklyR, growthR, topR, trendR].filter(
        (r) => r.status === "rejected",
      ).length;
      if (failed > 0) {
        message.warning(`일부 데이터를 불러오지 못했습니다 (${failed}건). 표시된 값만 갱신됨.`);
      }
    } catch {
      message.error("대시보드 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [year, month, topLanguage, topPlatform]);

  useEffect(() => {
    // 필터 변경 시 마케팅 대시보드 재요청 (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
  }, [fetchData]);

  // 전체 갱신: 모든 활성 계정 동기 일괄 수집 → 완료 후 대시보드 재요청.
  const handleRefreshAll = useCallback(async () => {
    setRefreshing(true);
    const hide = message.loading("전체 갱신 중… (수 초~수십 초 소요)", 0);
    try {
      const { data } = await refreshAll({ includeMetrics: true });
      hide();
      if (data.failed_count > 0) {
        message.warning(
          `갱신 완료 — 성공 ${data.ok_count}건, 실패 ${data.failed_count}건. ` +
            `실패 계정은 토큰/권한을 확인하세요.`,
        );
      } else {
        message.success(`전체 갱신 완료 — ${data.ok_count}개 계정 갱신됨.`);
      }
      // 부분 실패(메트릭만 실패 등) 사유를 추가로 안내.
      const partial = data.results.filter((r) => r.ok && r.errors.length > 0);
      if (partial.length > 0) {
        message.info(
          `일부 지표 미수집: ${partial
            .map((r) => `${r.platform}/${r.language}`)
            .join(", ")}`,
        );
      }
      await fetchData();
    } catch {
      hide();
      message.error("전체 갱신에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setRefreshing(false);
    }
  }, [fetchData]);

  // ----- Pivoted weekly rows + totals -----
  const weekNumbers = useMemo(() => deriveWeekNumbers(weeklyData), [weeklyData]);
  const pivotedRows = useMemo(() => pivotWeeklyRows(weeklyData), [weeklyData]);
  const totalRow = useMemo(
    () => buildTotalRow(pivotedRows, weekNumbers),
    [pivotedRows, weekNumbers],
  );

  // ----- 통합 요약: 플랫폼별 합산 + 전체 합계 -----
  const platformSummaries = useMemo(
    () => aggregateByPlatform(growthData, weeklyData),
    [growthData, weeklyData],
  );
  const totals = useMemo(
    () => computeTotals(platformSummaries, weeklyData),
    [platformSummaries, weeklyData],
  );

  return {
    year,
    setYear,
    month,
    setMonth,
    topLanguage,
    setTopLanguage,
    topPlatform,
    setTopPlatform,
    growthData,
    topPosts,
    trendData,
    loading,
    refreshing,
    handleRefreshAll,
    weekNumbers,
    pivotedRows,
    totalRow,
    platformSummaries,
    totals,
  };
}
