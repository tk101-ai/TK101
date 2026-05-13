import { Tabs, Typography } from "antd";
import LlmChatPanel from "../../components/playground/LlmChatPanel";
import PlaceholderTab from "../../components/playground/PlaceholderTab";

const { Title, Paragraph } = Typography;

/**
 * AI Playground 최상위 페이지 (T8 Phase 1).
 *
 * - 상단 탭: LLM Chat / Image Gen / Video Gen
 * - Phase 1은 LLM Chat만 콘텐츠, 나머지는 "준비 중" placeholder
 * - admin 전용 (App.tsx ProtectedRoute에서 `playground` 모듈 가드)
 */
export default function PlaygroundPage() {
  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          AI Playground
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          모델 비교 · 시스템 프롬프트 튜닝 · 토큰/지연 가시화 — 관리자 전용 콘솔
        </Paragraph>
      </div>

      <Tabs
        defaultActiveKey="llm"
        size="middle"
        items={[
          {
            key: "llm",
            label: "LLM Chat",
            children: <LlmChatPanel />,
          },
          {
            key: "image",
            label: "Image Gen",
            children: (
              <PlaceholderTab
                title="Image Gen — Phase 4 예정"
                description="fal.ai Flux 등 이미지 생성 모델 통합은 Phase 4에서 활성화됩니다."
              />
            ),
          },
          {
            key: "video",
            label: "Video Gen",
            children: (
              <PlaceholderTab
                title="Video Gen — Phase 5 예정"
                description="fal.ai Veo / Kling 등 비디오 생성 모델 통합은 Phase 5에서 활성화됩니다."
              />
            ),
          },
        ]}
      />
    </div>
  );
}
