import type { PlaygroundProvider } from "../../api/playground";

/**
 * 정적 fallback provider 카탈로그 (T8 Phase 1).
 *
 * 백엔드 `/api/playground/providers` 엔드포인트가 아직 안 떠있을 때,
 * 또는 호출 실패 시 UI가 비지 않도록 클라이언트 측 기본값을 보관한다.
 * Phase 3에서 OpenAI/Gemini 등이 enabled=true 로 백엔드에서 내려오면
 * 그 응답이 우선시된다.
 *
 * 그리드 9칸 자리(3×3)를 미리 채워두는 placeholder 카드들도 포함한다.
 */
// 2026-05-19 라이브 probe 결과 기반.
// 백엔드 응답이 우선이지만, 백엔드 응답 전 첫 paint 시점에 비지 않게 동기 fallback.
export const STATIC_PROVIDERS: PlaygroundProvider[] = [
  {
    key: "gemini",
    name: "Gemini",
    versionBadge: "5v",
    enabled: true,
    variants: [
      { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash", badge: "빠름" },
      { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "gemini-3-flash-preview", label: "Gemini 3 Flash Preview", badge: "PREVIEW" },
      { id: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro Preview", badge: "PREVIEW" },
      { id: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite Preview", badge: "PREVIEW" },
    ],
  },
  {
    key: "glm",
    name: "GLM (Zhipu)",
    versionBadge: "3v",
    enabled: true,
    variants: [
      { id: "glm-5", label: "GLM-5" },
      { id: "glm-5.1", label: "GLM-5.1", badge: "최신" },
      { id: "glm-5-turbo", label: "GLM-5 Turbo", badge: "빠름" },
    ],
  },
  {
    key: "kimi",
    name: "Kimi (Moonshot)",
    versionBadge: "1v",
    enabled: true,
    variants: [{ id: "kimi-k2.5", label: "Kimi K2.5" }],
  },
  {
    key: "minimax",
    name: "MiniMax",
    versionBadge: "1v",
    enabled: true,
    variants: [{ id: "minimax-m2.7", label: "MiniMax M2.7", badge: "최신" }],
  },
  {
    key: "deepseek",
    name: "DeepSeek",
    versionBadge: "1v",
    enabled: true,
    variants: [{ id: "deepseek-v3.2", label: "DeepSeek v3.2" }],
  },
  {
    key: "openai",
    name: "OpenAI",
    versionBadge: "1v",
    enabled: true,
    variants: [{ id: "gpt-5-chat", label: "GPT-5 Chat" }],
  },
];

// 가장 가볍고 저렴한 모델을 기본값으로.
export const DEFAULT_PROVIDER_KEY = "gemini" as const;
export const DEFAULT_MODEL_ID = "gemini-2.5-flash";
