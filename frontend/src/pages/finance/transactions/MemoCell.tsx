import { useState } from "react";
import { Button, Input, Popover, Typography } from "antd";

// ---------------------------------------------------------------------------
// 인라인 메모 셀 (Popover 편집)
// ---------------------------------------------------------------------------

interface MemoCellProps {
  value: string | null;
  onSave: (memo: string | null) => Promise<void> | void;
}

export function MemoCell({ value, onSave }: MemoCellProps) {
  // H-2 정리: 부모에서 `key={value ?? "__empty__"}` 로 재마운트시키므로
  // value prop 동기화용 useEffect 제거 (set-state-in-effect 회피).
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(draft.trim() === "" ? null : draft);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) setDraft(value ?? "");
      }}
      trigger="click"
      placement="topLeft"
      destroyTooltipOnHide
      content={
        <div style={{ width: 260 }}>
          <Input.TextArea
            autoFocus
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="메모를 입력하세요"
          />
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
            <Button size="small" onClick={() => setOpen(false)}>취소</Button>
            <Button size="small" type="primary" loading={saving} onClick={handleSave}>
              저장
            </Button>
          </div>
        </div>
      }
    >
      <Button type="link" size="small" style={{ padding: 0 }}>
        {value && value.length > 0 ? (
          <span title={value}>
            {value.length > 10 ? value.slice(0, 10) + "…" : value}
          </span>
        ) : (
          <Typography.Text type="secondary">메모 추가</Typography.Text>
        )}
      </Button>
    </Popover>
  );
}
