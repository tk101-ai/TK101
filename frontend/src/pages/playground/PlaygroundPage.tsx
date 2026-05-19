import { useState } from "react";
import { Space, Switch, Tabs, Tooltip, Typography } from "antd";
import { ExperimentOutlined } from "@ant-design/icons";
import ComparePanel from "../../components/playground/ComparePanel";
import LlmChatPanel from "../../components/playground/LlmChatPanel";
import MediaCompareView from "../../components/playground/MediaCompareView";
import MediaGenPanel from "../../components/playground/MediaGenPanel";

const { Title, Paragraph, Text } = Typography;

/**
 * AI Playground 최상위 페이지.
 *
 * 탭 구성:
 *   LLM Chat / Image Gen / Video Gen — 각 탭 안에 "비교 모드" 토글.
 *   토글 ON 시 N개 모델 동시 호출 (비용 N배 주의).
 *
 * 2026-05-19 변경:
 *   - 별도 "비교 모드" 탭 제거 → 각 카테고리 안으로 통합.
 *   - 이미지/영상 비교도 활성화.
 */

interface CompareToggleProps {
  value: boolean;
  onChange: (v: boolean) => void;
  hint: string;
}

function CompareToggle({ value, onChange, hint }: CompareToggleProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        marginBottom: 16,
        padding: "8px 14px",
        background: "rgba(24,144,255,0.06)",
        borderRadius: 8,
        border: "1px solid rgba(24,144,255,0.15)",
      }}
    >
      <ExperimentOutlined style={{ color: "#1677ff", fontSize: 16 }} />
      <Space size={8} style={{ flex: 1 }}>
        <Text strong style={{ fontSize: 13 }}>비교 모드</Text>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {hint}
        </Text>
      </Space>
      <Tooltip title={value ? "단일 모델로 전환" : "여러 모델 동시 실행"}>
        <Switch checked={value} onChange={onChange} size="small" />
      </Tooltip>
    </div>
  );
}

export default function PlaygroundPage() {
  const [llmCompare, setLlmCompare] = useState(false);
  const [imageCompare, setImageCompare] = useState(false);
  const [videoCompare, setVideoCompare] = useState(false);

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          AI Playground
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
          텍스트 · 이미지 · 영상 — 모델 비교 옵션 포함 · 단가는 변동 가능
        </Paragraph>
      </div>

      <Tabs
        defaultActiveKey="llm"
        size="middle"
        items={[
          {
            key: "llm",
            label: "LLM Chat",
            children: (
              <>
                <CompareToggle
                  value={llmCompare}
                  onChange={setLlmCompare}
                  hint="같은 프롬프트를 여러 LLM 모델에 동시 전송"
                />
                {llmCompare ? <ComparePanel /> : <LlmChatPanel />}
              </>
            ),
          },
          {
            key: "image",
            label: "Image Gen",
            children: (
              <>
                <CompareToggle
                  value={imageCompare}
                  onChange={setImageCompare}
                  hint="같은 프롬프트로 여러 이미지 모델 동시 생성"
                />
                {imageCompare ? (
                  <MediaCompareView kind="image" />
                ) : (
                  <MediaGenPanel kind="image" />
                )}
              </>
            ),
          },
          {
            key: "video",
            label: "Video Gen",
            children: (
              <>
                <CompareToggle
                  value={videoCompare}
                  onChange={setVideoCompare}
                  hint="같은 프롬프트로 여러 영상 모델 동시 생성"
                />
                {videoCompare ? (
                  <MediaCompareView kind="video" />
                ) : (
                  <MediaGenPanel kind="video" />
                )}
              </>
            ),
          },
        ]}
      />
    </div>
  );
}
