import { useCallback, useState } from "react";
import { message } from "antd";
import {
  classifyAttachment,
  deleteAttachment,
  uploadAttachment,
  MAX_ATTACHMENT_BYTES,
  type PlaygroundAttachment,
} from "../api/playground";

/**
 * 채팅 첨부 파일 상태 관리 hook.
 *
 * - 한 곳(LlmChatPanel)에서 소유하고 ChatInputBar + drop zone 모두 같은 상태를 공유.
 * - 파일 picker / drag&drop / chip 삭제 모두 동일 API.
 */
export function useChatAttachments(sessionId: string | null) {
  const [attachments, setAttachments] = useState<PlaygroundAttachment[]>([]);
  const [uploading, setUploading] = useState(false);

  const addFiles = useCallback(
    async (files: File[]): Promise<void> => {
      if (files.length === 0) return;
      setUploading(true);
      try {
        for (const f of files) {
          if (f.size > MAX_ATTACHMENT_BYTES) {
            message.warning(
              `${f.name}: 파일이 너무 큽니다 (최대 ${
                MAX_ATTACHMENT_BYTES / (1024 * 1024)
              }MB)`,
            );
            continue;
          }
          if (classifyAttachment(f) === null) {
            message.warning(`${f.name}: 지원하지 않는 형식`);
            continue;
          }
          try {
            const att = await uploadAttachment(f, sessionId ?? undefined);
            setAttachments((prev) => [...prev, att]);
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "업로드 실패";
            message.error(`${f.name}: ${msg}`);
          }
        }
      } finally {
        setUploading(false);
      }
    },
    [sessionId],
  );

  const remove = useCallback(async (id: string): Promise<void> => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
    try {
      await deleteAttachment(id);
    } catch {
      // 서버 삭제 실패해도 UI 에선 제거. 다음 청소 cron 으로 정리.
    }
  }, []);

  const clear = useCallback(() => {
    // addFiles 가 즉시 업로드하므로, 보내지 않은 첨부를 그냥 비우면 서버에 고아로 남는다.
    // remove() 처럼 각 첨부를 best-effort 로 서버 삭제한다(개별 실패는 무시).
    setAttachments((prev) => {
      prev.forEach((a) => {
        deleteAttachment(a.id).catch(() => {
          // 서버 삭제 실패해도 clear 를 막지 않음. 다음 청소 cron 으로 정리.
        });
      });
      return [];
    });
  }, []);

  return {
    attachments,
    uploading,
    addFiles,
    remove,
    clear,
  };
}
