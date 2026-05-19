import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Select,
  Space,
  Switch,
  Tooltip,
  Typography,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import { adminGetLogs } from "../../api/playground";

const { Title, Paragraph, Text } = Typography;

const TAIL_OPTIONS = [
  { value: 100, label: "100줄" },
  { value: 200, label: "200줄" },
  { value: 500, label: "500줄" },
  { value: 1000, label: "1000줄" },
];

const AUTO_REFRESH_MS = 10000;

/**
 * Playground 로그 (admin 전용).
 *
 * - tail 줄 수 + 새로고침 + 자동 새로고침 토글 (10초).
 * - 본문은 monospace `<pre>` 박스.
 */
export default function LogsPage() {
  const [tail, setTail] = useState(200);
  const [logText, setLogText] = useState("");
  const [loading, setLoading] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [lastFetched, setLastFetched] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    setLoading(true);
    try {
      const text = await adminGetLogs(tail);
      setLogText(text);
      setLastFetched(new Date().toLocaleTimeString());
    } catch {
      message.error("로그 조회 실패 (admin 권한 필요)");
    } finally {
      setLoading(false);
    }
  }, [tail]);

  useEffect(() => {
    void fetchLogs();
  }, [fetchLogs]);

  // 자동 새로고침.
  const intervalRef = useRef<number | null>(null);
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = window.setInterval(() => {
        void fetchLogs();
      }, AUTO_REFRESH_MS);
    }
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, fetchLogs]);

  return (
    <div style={{ maxWidth: 1400 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          Playground 로그
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
          백엔드 로그 마지막 N 줄 (admin 전용).
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Space size={6}>
            <Text style={{ fontSize: 12 }}>표시 줄 수</Text>
            <Select
              value={tail}
              onChange={setTail}
              options={TAIL_OPTIONS}
              style={{ width: 110 }}
              size="small"
            />
          </Space>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={() => void fetchLogs()}
            loading={loading}
            size="small"
          >
            새로고침
          </Button>
          <Tooltip title="10초마다 자동 새로고침">
            <Space size={6}>
              <Switch
                size="small"
                checked={autoRefresh}
                onChange={setAutoRefresh}
              />
              <Text style={{ fontSize: 12 }}>자동 (10초)</Text>
            </Space>
          </Tooltip>
          {lastFetched && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              마지막 갱신: {lastFetched}
            </Text>
          )}
        </Space>
      </Card>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <pre
          style={{
            margin: 0,
            padding: 12,
            background: "rgba(0,0,0,0.85)",
            color: "rgba(255,255,255,0.92)",
            fontFamily:
              'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace',
            fontSize: 12,
            lineHeight: 1.45,
            minHeight: 480,
            maxHeight: "calc(100vh - 320px)",
            overflow: "auto",
            whiteSpace: "pre-wrap",
            wordBreak: "break-word",
            borderRadius: 6,
          }}
        >
          {logText || (loading ? "로그를 불러오는 중…" : "(로그 없음)")}
        </pre>
      </Card>
    </div>
  );
}
