import { Input } from "antd";

interface SystemPromptBoxProps {
  value: string;
  onChange: (next: string) => void;
  disabled?: boolean;
}

/**
 * 시스템 프롬프트 입력 영역.
 * 빈 문자열이 기본값. 변경되면 새 세션부터 적용됨.
 */
export default function SystemPromptBox({ value, onChange, disabled }: SystemPromptBoxProps) {
  return (
    <Input.TextArea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder="(선택) 시스템 프롬프트를 입력하세요. 비워두면 모델 기본 동작."
      rows={4}
      disabled={disabled}
      style={{ fontSize: 12, resize: "vertical" }}
      maxLength={4000}
      showCount
    />
  );
}
