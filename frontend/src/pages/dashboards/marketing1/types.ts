// ----- Types for the Marketing1 (SNS) dashboard -----

export interface WeeklyKpiRow {
  language: string;
  platform: string;
  year: number;
  month: number;
  week_number: number;
  followers: number;
  post_count: number;
  view_count: number;
  reaction_count: number;
}

export interface GrowthCard {
  language: string;
  platform: string;
  // 채널 식별축 — 브랜드(광고주)·핸들. 백필 전 기존 계정은 client=null.
  handle: string | null;
  client: string | null;
  current_followers: number;
  prev_followers: number;
  growth_rate: number;
}

export interface TopPost {
  id: string | number;
  posted_at: string;
  title: string;
  language: string;
  platform: string;
  view_count: number;
  total_engagement: number;
  url: string;
}

export interface PivotedRow {
  key: string;
  language: string;
  platform: string;
  // 주차→팔로워. 5주차가 있는 달도 자동 반영(백엔드 week-of-month = ((day-1)//7)+1 → 최대 5).
  weeks: Record<number, number>;
  postCount: number;
  viewCount: number;
  reactionCount: number;
}

export interface PlatformSummary {
  platform: string;
  followers: number; // 최신 스냅샷 합산
  growthRate: number; // 가중 평균 성장률(팔로워 비중)
  postCount: number; // 이번 달 게시물 수
  viewCount: number;
}

export interface TotalsSummary {
  totalFollowers: number;
  followerGrowthRate: number;
  monthPostCount: number;
  totalViews: number;
  totalReactions: number;
  avgEngagementRate: number; // 반응수 / 조회수
}
