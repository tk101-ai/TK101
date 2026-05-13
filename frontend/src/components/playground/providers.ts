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
export const STATIC_PROVIDERS: PlaygroundProvider[] = [
  {
    key: "claude",
    name: "Claude",
    versionBadge: "3v",
    enabled: true,
    variants: [
      { id: "claude-haiku-4-5", label: "Haiku 4.5" },
      { id: "claude-sonnet-4-6", label: "Sonnet 4.6" },
      { id: "claude-opus-4-7", label: "Opus 4.7", badge: "NEW" },
    ],
  },
  {
    key: "openai",
    name: "OpenAI",
    versionBadge: "—",
    enabled: false,
    variants: [],
  },
  {
    key: "gemini",
    name: "Gemini",
    versionBadge: "—",
    enabled: false,
    variants: [],
  },
];

export const DEFAULT_PROVIDER_KEY = "claude" as const;
export const DEFAULT_MODEL_ID = "claude-haiku-4-5";
