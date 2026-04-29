import { Alert, Button, Progress, Space, Tag, Tooltip } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { NasIndexStatus, NasStatus } from "../../api/nas";
import { formatDateTime } from "./nasUtils";

interface NasStatusHeaderProps {
  status: NasStatus | null;
  indexStatus: NasIndexStatus | null;
  isAdmin: boolean;
  onRunIndex: () => void;
  runDisabled: boolean;
}

export default function NasStatusHeader({
  status,
  indexStatus,
  isAdmin,
  onRunIndex,
  runDisabled,
}: NasStatusHeaderProps) {
  const indexed = status?.indexed_files ?? 0;
  const total = status?.total_files ?? 0;
  const lastIndexedLabel = status?.last_indexed_at
    ? `최종 인덱싱: ${formatDateTime(status.last_indexed_at)}`
    : "인덱싱 이력 없음";

  const running = indexStatus?.running ?? false;
  const progressTotal = indexStatus?.total ?? 0;
  const progressDone = indexStatus?.processed ?? 0;
  const progressPercent =
    progressTotal > 0 ? Math.min(100, Math.round((progressDone / progressTotal) * 100)) : 0;

  return (
    <div style={{ marginBottom: 24 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            자료 검색
          </h2>
          <div style={{ color: "#8c8c8c", marginTop: 4, fontSize: 13 }}>
            NAS 문서를 의미 기반으로 검색합니다
          </div>
        </div>
        <Space size={12} wrap>
          <Tooltip title={lastIndexedLabel}>
            <Tag color={indexed > 0 ? "blue" : "default"} style={{ fontSize: 13, padding: "4px 10px" }}>
              인덱싱 {indexed.toLocaleString("ko-KR")} / {total.toLocaleString("ko-KR")}
            </Tag>
          </Tooltip>
          {isAdmin && (
            <Button
              icon={<ReloadOutlined />}
              onClick={onRunIndex}
              disabled={runDisabled || running}
              loading={running}
            >
              {running ? "인덱싱 진행 중" : "인덱스 다시 실행"}
            </Button>
          )}
        </Space>
      </div>

      {status && !status.mount_ok && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 16 }}
          message="NAS 마운트가 정상이 아닙니다"
          description={`경로: ${status.mount_path} — 시스템 관리자에게 문의하세요`}
        />
      )}

      {running && (
        <div style={{ marginTop: 16 }}>
          <Progress
            percent={progressPercent}
            status="active"
            format={() => `${progressDone.toLocaleString("ko-KR")} / ${progressTotal.toLocaleString("ko-KR")}`}
          />
          {indexStatus?.current_path && (
            <div style={{ color: "#8c8c8c", fontSize: 12, marginTop: 4 }}>
              처리 중: {indexStatus.current_path}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
