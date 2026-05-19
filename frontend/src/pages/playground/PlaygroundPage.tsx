import { Tabs, Typography } from "antd";
import ComparePanel from "../../components/playground/ComparePanel";
import LlmChatPanel from "../../components/playground/LlmChatPanel";
import MediaGenPanel from "../../components/playground/MediaGenPanel";

const { Title, Paragraph } = Typography;

/**
 * AI Playground 최상위 페이지.
 *
 * - 상단 탭: LLM Chat / Image Gen / Video Gen
 * - Image/Video 는 Phase 4/5 뼈대 — 텐센트 CreateAigcImageTask · CreateAigcVideoTask
 *   호출 + 폴링. DB 영속화 없음 (뼈대 단계).
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
          모델 비교 · 시스템 프롬프트 튜닝 · 이미지/영상 생성 — 관리자 전용 콘솔
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
            key: "compare",
            label: "비교 모드",
            children: <ComparePanel />,
          },
          {
            key: "image",
            label: "Image Gen",
            children: <MediaGenPanel kind="image" />,
          },
          {
            key: "video",
            label: "Video Gen",
            children: <MediaGenPanel kind="video" />,
          },
        ]}
      />
    </div>
  );
}
