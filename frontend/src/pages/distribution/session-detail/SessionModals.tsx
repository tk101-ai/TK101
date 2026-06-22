import { useEffect, useState } from "react";
import { DatePicker, Form, Input, Modal, Typography } from "antd";
import type { Dayjs } from "dayjs";

const { Paragraph } = Typography;
const { TextArea } = Input;

interface ApproveModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onConfirm: (scheduledStart: string | null) => Promise<void>;
}

export function ApproveModal({ open, loading, onClose, onConfirm }: ApproveModalProps) {
  const [scheduled, setScheduled] = useState<Dayjs | null>(null);

  useEffect(() => {
    if (!open) setScheduled(null);
  }, [open]);

  const handleOk = async () => {
    await onConfirm(scheduled ? scheduled.toISOString() : null);
  };

  return (
    <Modal
      title="세션 승인"
      open={open}
      onCancel={onClose}
      onOk={() => {
        void handleOk();
      }}
      okText="승인"
      cancelText="취소"
      confirmLoading={loading}
      destroyOnClose
    >
      <Paragraph>
        승인 후 워커가 픽업하여 송신합니다. 예약 시각을 비워두면 즉시 송신
        가능 상태로 전환됩니다.
      </Paragraph>
      <Form layout="vertical">
        <Form.Item label="예약 송신 시각 (선택)">
          <DatePicker
            showTime
            value={scheduled}
            onChange={setScheduled}
            style={{ width: "100%" }}
            format="YYYY-MM-DD HH:mm"
            placeholder="비워두면 즉시 송신 가능"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

interface RejectModalProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => Promise<void>;
}

export function RejectModal({ open, loading, onClose, onConfirm }: RejectModalProps) {
  const [reason, setReason] = useState<string>("");

  useEffect(() => {
    if (!open) setReason("");
  }, [open]);

  const handleOk = async () => {
    await onConfirm(reason.trim());
  };

  return (
    <Modal
      title="세션 거부"
      open={open}
      onCancel={onClose}
      onOk={() => {
        void handleOk();
      }}
      okText="거부"
      okType="danger"
      cancelText="취소"
      confirmLoading={loading}
      destroyOnClose
    >
      <Paragraph>거부 사유를 남기면 운영 로그에 기록됩니다 (선택).</Paragraph>
      <TextArea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        autoSize={{ minRows: 3, maxRows: 6 }}
        maxLength={500}
        showCount
        placeholder="예: 톤 어색함, 가격 정보 오타"
      />
    </Modal>
  );
}
