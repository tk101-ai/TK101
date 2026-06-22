import { Link, useParams } from "react-router-dom";
import { Button, Empty, Spin, Typography } from "antd";
import { ArrowLeftOutlined } from "@ant-design/icons";
import { useAuth } from "../../hooks/useAuth";
import { useSessionDetail } from "./session-detail/useSessionDetail";
import { SessionHeaderCard } from "./session-detail/SessionHeaderCard";
import { MessageTimeline } from "./session-detail/MessageTimeline";
import { AddMessageCard } from "./session-detail/AddMessageCard";
import { ApproveModal, RejectModal } from "./session-detail/SessionModals";

const { Title, Paragraph } = Typography;

/**
 * 세션 상세 + 메시지 타임라인 검수 화면 (T9 Phase C).
 *
 * - 상단 카드: 시나리오/발신·수신/상태/생성일/비용 + 상태별 액션 버튼.
 * - 타임라인: 메시지 1행씩, 인라인 편집 → `PATCH /messages/{id}`.
 * - 액션:
 *   - status=pending → [승인] / [거부]
 *   - status=approved → [지금 송신] / [거부로 변경]
 *   - status=sent → 송신 완료 안내만.
 *
 * 본문은 얇은 컨테이너로, 데이터·상태는 `useSessionDetail` 훅에,
 * UI 는 `session-detail/` 하위 컴포넌트로 분리했다(동작 동일).
 */
export default function SessionDetailPage() {
  const { id } = useParams<{ id: string }>();
  // 승인/거부는 신사업팀 member 가능(검수), 실 송신(send-now)만 백엔드
  // require_admin → member 에게는 '지금 송신' 버튼을 숨겨 403 혼란을 막는다.
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const {
    detail,
    loading,
    session,
    messages,
    cumulativeOffsets,
    fetchData,
    handleMessageSaved,
    handleDeleteMessage,
    approveOpen,
    setApproveOpen,
    rejectOpen,
    setRejectOpen,
    actionLoading,
    sendNowLoading,
    handleApprove,
    handleReject,
    handleSendNow,
    addSide,
    setAddSide,
    addContent,
    setAddContent,
    addAfterSec,
    setAddAfterSec,
    adding,
    handleAddMessage,
  } = useSessionDetail(id);

  if (!id) {
    return <Empty description="세션 ID 가 없습니다" />;
  }

  if (loading && !detail) {
    return (
      <div style={{ display: "flex", justifyContent: "center", padding: 64 }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!session) {
    return (
      <div style={{ maxWidth: 720 }}>
        <Empty description="세션을 찾을 수 없습니다" />
        <div style={{ marginTop: 16, textAlign: "center" }}>
          <Link to="/distribution/sessions">
            <Button icon={<ArrowLeftOutlined />}>목록으로</Button>
          </Link>
        </div>
      </div>
    );
  }

  const status = session.status;
  // 예약/송신중/완료 세션은 편집 불가 (워커가 송신 중이거나 이미 송신됨).
  const editingDisabled =
    status === "sent" || status === "sending" || status === "scheduled";
  // 예약 세션 계열에서만 메시지별 워커 송신 상태(send_state)를 노출.
  const showSendState =
    status === "scheduled" || status === "sending" || status === "sent";

  return (
    <div style={{ maxWidth: 1080 }}>
      <div style={{ marginBottom: 16 }}>
        <Link to="/distribution/sessions">
          <Button type="link" icon={<ArrowLeftOutlined />} style={{ paddingLeft: 0 }}>
            목록으로
          </Button>
        </Link>
      </div>

      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          세션 상세
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          메시지 본문을 클릭해 편집한 뒤 승인 또는 즉시 송신할 수 있습니다.
        </Paragraph>
      </div>

      <SessionHeaderCard
        session={session}
        messages={messages}
        isAdmin={isAdmin}
        sendNowLoading={sendNowLoading}
        onRefresh={() => {
          void fetchData();
        }}
        onApproveOpen={() => setApproveOpen(true)}
        onRejectOpen={() => setRejectOpen(true)}
        onSendNow={() => {
          void handleSendNow();
        }}
      />

      <MessageTimeline
        messages={messages}
        cumulativeOffsets={cumulativeOffsets}
        editingDisabled={editingDisabled}
        showSendState={showSendState}
        onSaved={handleMessageSaved}
        onDeleteMessage={(messageId) => {
          void handleDeleteMessage(messageId);
        }}
      />

      {status === "pending" && (
        <AddMessageCard
          senderLabel={session.sender_account_label}
          receiverLabel={session.receiver_account_label}
          addSide={addSide}
          setAddSide={setAddSide}
          addContent={addContent}
          setAddContent={setAddContent}
          addAfterSec={addAfterSec}
          setAddAfterSec={setAddAfterSec}
          adding={adding}
          onAdd={() => {
            void handleAddMessage();
          }}
        />
      )}

      <ApproveModal
        open={approveOpen}
        loading={actionLoading}
        onClose={() => setApproveOpen(false)}
        onConfirm={handleApprove}
      />

      <RejectModal
        open={rejectOpen}
        loading={actionLoading}
        onClose={() => setRejectOpen(false)}
        onConfirm={handleReject}
      />
    </div>
  );
}
