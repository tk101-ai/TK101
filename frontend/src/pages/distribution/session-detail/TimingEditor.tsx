import { useState } from "react";
import { Button, InputNumber, Select, Space, message } from "antd";
import {
  updateMessageTiming,
  type MessageItem,
} from "../../../api/distribution";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { TIMING_PRESETS } from "./formatters";

interface TimingEditorProps {
  msg: MessageItem;
  disabled: boolean;
  onUpdated: (next: MessageItem) => void;
}

export function TimingEditor({ msg, disabled, onUpdated }: TimingEditorProps) {
  const [editing, setEditing] = useState<boolean>(false);
  const [value, setValue] = useState<number>(msg.send_after_sec);
  const [saving, setSaving] = useState<boolean>(false);

  const submit = async (next: number) => {
    if (next < 0 || next > 86400) {
      message.warning("0초 ~ 24시간(86400초) 범위만 가능합니다.");
      return;
    }
    setSaving(true);
    try {
      const updated = await updateMessageTiming(msg.id, next);
      message.success(`메시지 #${msg.order_index + 1} 텀 변경: +${next}s`);
      onUpdated(updated);
      setEditing(false);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "텀 변경 실패"));
    } finally {
      setSaving(false);
    }
  };

  if (disabled || msg.status === "sent") {
    return null;
  }

  if (!editing) {
    return (
      <Button
        size="small"
        type="link"
        style={{ padding: 0, fontSize: 12 }}
        onClick={() => {
          setValue(msg.send_after_sec);
          setEditing(true);
        }}
      >
        텀 변경
      </Button>
    );
  }

  return (
    <Space size={4} wrap style={{ fontSize: 12 }}>
      <InputNumber
        size="small"
        min={0}
        max={86400}
        value={value}
        onChange={(v) => setValue(typeof v === "number" ? v : 0)}
        disabled={saving}
        style={{ width: 80 }}
        addonAfter="초"
      />
      <Select
        size="small"
        value={undefined}
        placeholder="프리셋"
        options={TIMING_PRESETS.map((p) => ({ label: p.label, value: p.value }))}
        onChange={(v) => {
          if (typeof v === "number") setValue(v);
        }}
        style={{ width: 90 }}
        disabled={saving}
      />
      <Button
        size="small"
        type="primary"
        loading={saving}
        onClick={() => {
          void submit(value);
        }}
      >
        적용
      </Button>
      <Button
        size="small"
        onClick={() => setEditing(false)}
        disabled={saving}
      >
        취소
      </Button>
    </Space>
  );
}
