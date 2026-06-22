import { Alert, Button, Card, Descriptions, Popconfirm, Space, Tag, Typography } from "antd";
import {
  CheckOutlined,
  CloseOutlined,
  ReloadOutlined,
  SendOutlined,
  StopOutlined,
} from "@ant-design/icons";
import {
  DISTRIBUTION_LANGUAGE_LABEL,
  DISTRIBUTION_LANGUAGE_TAG_COLOR,
  SESSION_STATUS_LABEL,
  SESSION_STATUS_TAG_COLOR,
  type MessageItem,
  type SessionDetail,
} from "../../../api/distribution";
import { formatCost, formatDateTime } from "./formatters";

const { Text } = Typography;

type SessionInfo = SessionDetail["session"];

interface SessionHeaderCardProps {
  session: SessionInfo;
  messages: MessageItem[];
  isAdmin: boolean;
  sendNowLoading: boolean;
  onRefresh: () => void;
  onApproveOpen: () => void;
  onRejectOpen: () => void;
  onSendNow: () => void;
}

export function SessionHeaderCard({
  session,
  messages,
  isAdmin,
  sendNowLoading,
  onRefresh,
  onApproveOpen,
  onRejectOpen,
  onSendNow,
}: SessionHeaderCardProps) {
  const status = session.status;

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <Space>
          <Text strong>{session.scenario_name}</Text>
          <Tag color={SESSION_STATUS_TAG_COLOR[status]}>
            {SESSION_STATUS_LABEL[status]}
          </Tag>
        </Space>
      }
      extra={
        <Space wrap>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              onRefresh();
            }}
          >
            새로고침
          </Button>
          {status === "pending" && (
            <>
              <Button
                type="primary"
                icon={<CheckOutlined />}
                onClick={onApproveOpen}
              >
                승인
              </Button>
              <Button
                danger
                icon={<CloseOutlined />}
                onClick={onRejectOpen}
              >
                거부
              </Button>
            </>
          )}
          {status === "approved" && (
            <>
              {isAdmin && (
                <Popconfirm
                  title="지금 바로 송신할까요?"
                  description="송신 결과가 즉시 반영됩니다."
                  okText="송신"
                  cancelText="취소"
                  onConfirm={() => {
                    onSendNow();
                  }}
                >
                  <Button
                    type="primary"
                    icon={<SendOutlined />}
                    loading={sendNowLoading}
                  >
                    지금 송신
                  </Button>
                </Popconfirm>
              )}
              <Button
                danger
                icon={<StopOutlined />}
                onClick={onRejectOpen}
              >
                거부로 변경
              </Button>
            </>
          )}
        </Space>
      }
    >
      <Descriptions size="small" column={2} bordered>
        <Descriptions.Item label="발신">
          {session.sender_account_label}
        </Descriptions.Item>
        <Descriptions.Item label="수신">
          {session.receiver_account_label}
        </Descriptions.Item>
        <Descriptions.Item label="대화 언어">
          <Tag
            color={
              DISTRIBUTION_LANGUAGE_TAG_COLOR[session.language] ?? "default"
            }
          >
            {DISTRIBUTION_LANGUAGE_LABEL[session.language] ?? session.language}
          </Tag>
        </Descriptions.Item>
        <Descriptions.Item label="메시지 수">
          {session.message_count}
        </Descriptions.Item>
        <Descriptions.Item label="비용 (USD)">
          {formatCost(session.llm_cost_usd)}
        </Descriptions.Item>
        <Descriptions.Item label="생성일">
          {formatDateTime(session.generated_at)}
        </Descriptions.Item>
        <Descriptions.Item label="승인일">
          {formatDateTime(session.approved_at)}
        </Descriptions.Item>
        <Descriptions.Item label="예약 송신">
          {formatDateTime(session.scheduled_start)}
        </Descriptions.Item>
        <Descriptions.Item label="완료일">
          {formatDateTime(session.completed_at)}
        </Descriptions.Item>
      </Descriptions>

      {session.scenario_attachment_required && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          message="이 시나리오는 파일 첨부가 권장됩니다 (예: VIP 프로모션 — 엑셀)"
          description={(() => {
            const total = messages.length;
            const withAttachment = messages.filter(
              (m) => m.attachment_url != null,
            ).length;
            if (total === 0) return "메시지가 없습니다.";
            if (withAttachment === 0) {
              return `숫자·상세 정보는 엑셀로만 전달하는 것이 시나리오 취지입니다. 현재 첨부된 메시지가 없습니다 (${total}건 중 0건). 송신 전 1건 이상에 엑셀 파일을 첨부하세요.`;
            }
            return `현재 ${total}건 중 ${withAttachment}건에 첨부가 포함되어 있습니다.`;
          })()}
        />
      )}
      {status === "sent" && (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 16 }}
          message="송신이 완료된 세션입니다."
          description="이 세션은 더 이상 편집할 수 없습니다."
        />
      )}
      {status === "failed" && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 16 }}
          message="송신에 실패한 세션입니다."
          description="문제 메시지를 확인한 뒤 필요 시 재승인하거나 거부 처리하세요."
        />
      )}
      {status === "rejected" && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 16 }}
          message="거부된 세션입니다."
        />
      )}
      {status === "scheduled" && (
        <Alert
          type="info"
          showIcon
          style={{ marginTop: 16 }}
          message={`예약 송신 대기 중입니다 (예약 시각: ${formatDateTime(session.scheduled_start)}).`}
          description="백그라운드 워커가 각 메시지의 예정 시각에 자동 송신합니다. 메시지별 진행 상태는 타임라인에서 확인하세요."
        />
      )}
      {status === "sending" && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 16 }}
          message="송신이 진행 중입니다."
          description="워커가 작업을 끝낼 때까지 편집·재승인은 권장하지 않습니다."
        />
      )}
    </Card>
  );
}
