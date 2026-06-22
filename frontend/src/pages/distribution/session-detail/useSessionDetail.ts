import { useCallback, useEffect, useMemo, useState } from "react";
import { Modal, message } from "antd";
import {
  SESSION_STATUS_LABEL,
  addMessage,
  approveSession,
  deleteMessage,
  getSession,
  rejectSession,
  sendSessionNow,
  type MessageItem,
  type SessionDetail,
} from "../../../api/distribution";
import { extractErrorDetail } from "../../../utils/errorUtils";

/**
 * 세션 상세 화면의 데이터·상태·핸들러를 모은 훅 (순수 리팩토링).
 *
 * SessionDetailPage 본문에 인라인되어 있던 fetch/편집/승인/거부/송신 로직을
 * 그대로 옮긴 것으로 동작은 동일하다.
 */
export function useSessionDetail(id: string | undefined) {
  const [detail, setDetail] = useState<SessionDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [approveOpen, setApproveOpen] = useState<boolean>(false);
  const [rejectOpen, setRejectOpen] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [sendNowLoading, setSendNowLoading] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    try {
      const next = await getSession(id);
      setDetail(next);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 상세 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  const session = detail?.session ?? null;
  const messages = useMemo(() => detail?.messages ?? [], [detail]);

  // 누적 send_after_sec — 메시지 순서대로 합산.
  const cumulativeOffsets = useMemo(() => {
    const offsets: number[] = [];
    let acc = 0;
    for (const msg of messages) {
      acc += msg.send_after_sec;
      offsets.push(acc);
    }
    return offsets;
  }, [messages]);

  const handleMessageSaved = useCallback((next: MessageItem) => {
    setDetail((current) => {
      if (!current) return current;
      return {
        ...current,
        messages: current.messages.map((m) => (m.id === next.id ? next : m)),
      };
    });
  }, []);

  // 타임라인 직접 편집 — 메시지 삭제 / 추가.
  const handleDeleteMessage = useCallback(
    async (messageId: string) => {
      try {
        await deleteMessage(messageId);
        message.success("메시지를 삭제했습니다.");
        await fetchData();
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "메시지 삭제 실패"));
      }
    },
    [fetchData],
  );

  const [addSide, setAddSide] = useState<"sender" | "receiver">("sender");
  const [addContent, setAddContent] = useState<string>("");
  const [addAfterSec, setAddAfterSec] = useState<number>(0);
  const [adding, setAdding] = useState<boolean>(false);

  const handleAddMessage = useCallback(async () => {
    if (!id) return;
    const content = addContent.trim();
    if (!content) {
      message.warning("메시지 내용을 입력하세요.");
      return;
    }
    setAdding(true);
    try {
      await addMessage(id, {
        sender: addSide,
        content,
        send_after_sec: addAfterSec,
      });
      message.success("메시지를 추가했습니다.");
      setAddContent("");
      setAddAfterSec(0);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "메시지 추가 실패"));
    } finally {
      setAdding(false);
    }
  }, [id, addContent, addSide, addAfterSec, fetchData]);

  const handleApprove = async (scheduledStart: string | null) => {
    if (!session) return;
    setActionLoading(true);
    try {
      await approveSession(session.id, scheduledStart);
      message.success("세션을 승인했습니다.");
      setApproveOpen(false);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "승인 실패"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async (reason: string) => {
    if (!session) return;
    setActionLoading(true);
    try {
      await rejectSession(session.id, reason.length > 0 ? reason : undefined);
      message.success("세션을 거부했습니다.");
      setRejectOpen(false);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "거부 실패"));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSendNow = async () => {
    if (!session) return;
    setSendNowLoading(true);
    try {
      const res = await sendSessionNow(session.id);
      // 부분 실패라도 res.error 가 있으면 사용자에게 첫 실패 원인 같이 노출.
      if (res.status === "failed") {
        Modal.error({
          title: `송신 실패 (${res.failed_count}건 실패 / ${res.sent_count}건 성공)`,
          content: res.error ?? "알 수 없는 오류 — 서버 로그를 확인하세요.",
          width: 600,
        });
      } else if (res.failed_count > 0) {
        Modal.warning({
          title: `부분 성공 (${res.sent_count}건 송신 / ${res.failed_count}건 실패)`,
          content: res.error ?? "일부 메시지 실패 — 검수 화면에서 확인하세요.",
          width: 600,
        });
      } else if (res.status === "sent") {
        message.success(`송신 완료 — ${res.sent_count}건`);
      } else {
        message.info(`상태: ${SESSION_STATUS_LABEL[res.status]}`);
      }
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "송신 실패"));
    } finally {
      setSendNowLoading(false);
    }
  };

  return {
    detail,
    loading,
    session,
    messages,
    cumulativeOffsets,
    fetchData,
    handleMessageSaved,
    handleDeleteMessage,
    // 모달 상태
    approveOpen,
    setApproveOpen,
    rejectOpen,
    setRejectOpen,
    actionLoading,
    sendNowLoading,
    handleApprove,
    handleReject,
    handleSendNow,
    // 메시지 추가
    addSide,
    setAddSide,
    addContent,
    setAddContent,
    addAfterSec,
    setAddAfterSec,
    adding,
    handleAddMessage,
  };
}
