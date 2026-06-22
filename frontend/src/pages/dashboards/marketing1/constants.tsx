import type { ReactNode } from "react";
import dayjs from "dayjs";
import {
  YoutubeFilled,
  FacebookFilled,
  InstagramFilled,
} from "@ant-design/icons";

// ----- Label Maps -----
export const LANGUAGE_LABELS: Record<string, string> = {
  en: "영문",
  zh: "중간체",
  ja: "일문",
};

export const PLATFORM_LABELS: Record<string, string> = {
  facebook: "페이스북",
  instagram: "인스타",
  twitter: "트위터(X)",
  youtube: "유튜브",
  weibo: "웨이보",
};

export const LANGUAGE_OPTIONS = [
  { value: "all", label: "전체 어권" },
  { value: "en", label: "영문" },
  { value: "zh", label: "중간체" },
  { value: "ja", label: "일문" },
];

export const PLATFORM_OPTIONS = [
  { value: "all", label: "전체 플랫폼" },
  { value: "facebook", label: "페이스북" },
  { value: "instagram", label: "인스타" },
  { value: "twitter", label: "트위터(X)" },
  { value: "youtube", label: "유튜브" },
  { value: "weibo", label: "웨이보" },
];

export const formatNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return "0";
  return Number(value).toLocaleString("ko-KR");
};

export const formatPercent = (value: number): string => {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

// Year/month select options
const currentYear = dayjs().year();
export const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => ({
  value: currentYear - i,
  label: `${currentYear - i}년`,
}));
export const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}월`,
}));

// ----- Per-platform aggregation for the unified summary -----
export const PLATFORM_ICONS: Record<string, ReactNode> = {
  youtube: <YoutubeFilled style={{ color: "#ff0000" }} />,
  facebook: <FacebookFilled style={{ color: "#1877f2" }} />,
  instagram: <InstagramFilled style={{ color: "#d62976" }} />,
};

export const PLATFORM_DISPLAY_ORDER = ["youtube", "facebook", "instagram"];
