import { PLATFORM_DISPLAY_ORDER } from "./constants";
import type {
  WeeklyKpiRow,
  GrowthCard,
  PivotedRow,
  PlatformSummary,
  TotalsSummary,
} from "./types";

// 데이터에 등장한 주차 집합을 오름차순으로 도출(5주차 달이면 자동 포함).
export function deriveWeekNumbers(rows: WeeklyKpiRow[]): number[] {
  const set = new Set<number>();
  for (const row of rows) {
    if (Number.isFinite(row.week_number)) set.add(row.week_number);
  }
  // 데이터가 없으면 최소 1~4주 컬럼은 유지(빈 표에서도 헤더가 자연스럽게 보이도록).
  if (set.size === 0) return [1, 2, 3, 4];
  return Array.from(set).sort((a, b) => a - b);
}

// Pivot: (language, platform, week_number) → row per (language+platform) with week columns
export function pivotWeeklyRows(rows: WeeklyKpiRow[]): PivotedRow[] {
  const grouped = new Map<string, PivotedRow>();
  for (const row of rows) {
    const key = `${row.language}__${row.platform}`;
    const existing = grouped.get(key) ?? {
      key,
      language: row.language,
      platform: row.platform,
      weeks: {},
      postCount: 0,
      viewCount: 0,
      reactionCount: 0,
    };
    const next: PivotedRow = { ...existing, weeks: { ...existing.weeks } };
    next.weeks[row.week_number] = row.followers;
    next.postCount += row.post_count ?? 0;
    next.viewCount += row.view_count ?? 0;
    next.reactionCount += row.reaction_count ?? 0;
    grouped.set(key, next);
  }
  // Stable sort: language order (en, zh, ja), then platform order
  const langOrder = ["en", "zh", "ja"];
  const platformOrder = ["facebook", "instagram", "twitter", "youtube", "weibo"];
  return Array.from(grouped.values()).sort((a, b) => {
    const li = langOrder.indexOf(a.language);
    const lj = langOrder.indexOf(b.language);
    if (li !== lj) return li - lj;
    const pi = platformOrder.indexOf(a.platform);
    const pj = platformOrder.indexOf(b.platform);
    return pi - pj;
  });
}

export function buildTotalRow(
  rows: PivotedRow[],
  weekNumbers: number[],
): PivotedRow {
  return rows.reduce<PivotedRow>(
    (acc, row) => {
      const weeks = { ...acc.weeks };
      for (const w of weekNumbers) {
        weeks[w] = (weeks[w] ?? 0) + (row.weeks[w] ?? 0);
      }
      return {
        ...acc,
        weeks,
        postCount: acc.postCount + row.postCount,
        viewCount: acc.viewCount + row.viewCount,
        reactionCount: acc.reactionCount + row.reactionCount,
      };
    },
    {
      key: "__total__",
      language: "__total__",
      platform: "__total__",
      weeks: {},
      postCount: 0,
      viewCount: 0,
      reactionCount: 0,
    },
  );
}

// growth(채널별 최신/직전 팔로워) + weekly(게시물 집계)를 platform 단위로 합산.
export function aggregateByPlatform(
  growth: GrowthCard[],
  weekly: WeeklyKpiRow[],
): PlatformSummary[] {
  const byPlatform = new Map<string, PlatformSummary>();
  const ensure = (platform: string): PlatformSummary => {
    const existing = byPlatform.get(platform);
    if (existing) return existing;
    const fresh: PlatformSummary = {
      platform,
      followers: 0,
      growthRate: 0,
      postCount: 0,
      viewCount: 0,
    };
    byPlatform.set(platform, fresh);
    return fresh;
  };

  // 팔로워 + 성장률(가중합 누적 → 마지막에 나눔). prev 합으로 가중.
  const prevByPlatform = new Map<string, number>();
  for (const card of growth) {
    const row = ensure(card.platform);
    row.followers += card.current_followers;
    const prev = prevByPlatform.get(card.platform) ?? 0;
    prevByPlatform.set(card.platform, prev + card.prev_followers);
  }
  for (const [platform, prevSum] of prevByPlatform) {
    const row = byPlatform.get(platform);
    if (row && prevSum > 0) {
      row.growthRate = (row.followers - prevSum) / prevSum;
    }
  }

  // 게시물 수 / 조회수 (이번 달, 주차 합산).
  for (const r of weekly) {
    const row = ensure(r.platform);
    row.postCount += r.post_count ?? 0;
    row.viewCount += r.view_count ?? 0;
  }

  return Array.from(byPlatform.values()).sort((a, b) => {
    const ai = PLATFORM_DISPLAY_ORDER.indexOf(a.platform);
    const bi = PLATFORM_DISPLAY_ORDER.indexOf(b.platform);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

export function computeTotals(
  platforms: PlatformSummary[],
  weekly: WeeklyKpiRow[],
): TotalsSummary {
  const totalFollowers = platforms.reduce((s, p) => s + p.followers, 0);
  const prevFollowers = platforms.reduce(
    (s, p) =>
      s + (p.growthRate !== 0 ? p.followers / (1 + p.growthRate) : p.followers),
    0,
  );
  const followerGrowthRate =
    prevFollowers > 0 ? (totalFollowers - prevFollowers) / prevFollowers : 0;

  const monthPostCount = weekly.reduce((s, r) => s + (r.post_count ?? 0), 0);
  const totalViews = weekly.reduce((s, r) => s + (r.view_count ?? 0), 0);
  const totalReactions = weekly.reduce((s, r) => s + (r.reaction_count ?? 0), 0);
  const avgEngagementRate = totalViews > 0 ? totalReactions / totalViews : 0;

  return {
    totalFollowers,
    followerGrowthRate,
    monthPostCount,
    totalViews,
    totalReactions,
    avgEngagementRate,
  };
}
