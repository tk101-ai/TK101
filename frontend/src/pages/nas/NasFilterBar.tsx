import { Radio, Select, Space, Tag } from "antd";
import type { RadioChangeEvent } from "antd";
import type { NasFileKind } from "../../api/nas";

export type NasPeriodKey = "all" | "1w" | "1m" | "3m" | "1y";

export interface NasFilterValue {
  fileKinds: NasFileKind[];
  pathPrefix: string | null;
  period: NasPeriodKey;
}

export interface NasFilterBarProps {
  value: NasFilterValue;
  onChange: (next: NasFilterValue) => void;
  folders: string[];
}

interface FileKindOption {
  key: "all" | NasFileKind;
  label: string;
}

const FILE_KIND_OPTIONS: FileKindOption[] = [
  { key: "all", label: "전체" },
  { key: "pdf", label: "PDF" },
  { key: "word", label: "Word" },
  { key: "ppt", label: "PPT" },
];

interface PeriodOption {
  key: NasPeriodKey;
  label: string;
}

const PERIOD_OPTIONS: PeriodOption[] = [
  { key: "all", label: "전체" },
  { key: "1w", label: "1주" },
  { key: "1m", label: "1개월" },
  { key: "3m", label: "3개월" },
  { key: "1y", label: "1년" },
];

/**
 * `period` 키를 ISO mtime_from 문자열로 변환한다.
 * "전체"면 undefined를 반환해 백엔드 측에서 필터를 제외하도록 한다.
 */
export function periodToMtimeFrom(period: NasPeriodKey, now: Date = new Date()): string | undefined {
  if (period === "all") return undefined;
  const from = new Date(now.getTime());
  switch (period) {
    case "1w":
      from.setDate(from.getDate() - 7);
      break;
    case "1m":
      from.setMonth(from.getMonth() - 1);
      break;
    case "3m":
      from.setMonth(from.getMonth() - 3);
      break;
    case "1y":
      from.setFullYear(from.getFullYear() - 1);
      break;
  }
  return from.toISOString();
}

export default function NasFilterBar({ value, onChange, folders }: NasFilterBarProps) {
  const isAllKindsSelected = value.fileKinds.length === 0;

  const handleKindToggle = (key: "all" | NasFileKind, checked: boolean) => {
    if (key === "all") {
      // "전체"를 누르면 모든 형식 해제 (해제 = 전체)
      if (!isAllKindsSelected) {
        onChange({ ...value, fileKinds: [] });
      }
      return;
    }
    const current = new Set<NasFileKind>(value.fileKinds);
    if (checked) {
      current.add(key);
    } else {
      current.delete(key);
    }
    onChange({ ...value, fileKinds: Array.from(current) });
  };

  const handleFolderChange = (next: string | undefined) => {
    onChange({ ...value, pathPrefix: next ?? null });
  };

  const handlePeriodChange = (e: RadioChangeEvent) => {
    onChange({ ...value, period: e.target.value as NasPeriodKey });
  };

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: "10px 18px",
        padding: "8px 0 14px",
        marginBottom: 12,
      }}
    >
      <FilterGroup label="형식">
        <Space size={6} wrap>
          {FILE_KIND_OPTIONS.map((opt) => {
            const checked =
              opt.key === "all" ? isAllKindsSelected : value.fileKinds.includes(opt.key);
            return (
              <Tag.CheckableTag
                key={opt.key}
                checked={checked}
                onChange={(next) => handleKindToggle(opt.key, next)}
                style={{
                  padding: "2px 12px",
                  fontSize: 13,
                  border: "1px solid #d9d9d9",
                }}
              >
                {opt.label}
              </Tag.CheckableTag>
            );
          })}
        </Space>
      </FilterGroup>

      <FilterGroup label="폴더">
        <Select<string>
          allowClear
          placeholder="전체 폴더"
          value={value.pathPrefix ?? undefined}
          onChange={handleFolderChange}
          options={folders.map((f) => ({ label: f, value: f }))}
          style={{ minWidth: 180 }}
          size="middle"
        />
      </FilterGroup>

      <FilterGroup label="기간">
        <Radio.Group
          value={value.period}
          onChange={handlePeriodChange}
          optionType="button"
          buttonStyle="solid"
          size="middle"
        >
          {PERIOD_OPTIONS.map((opt) => (
            <Radio.Button key={opt.key} value={opt.key}>
              {opt.label}
            </Radio.Button>
          ))}
        </Radio.Group>
      </FilterGroup>
    </div>
  );
}

interface FilterGroupProps {
  label: string;
  children: React.ReactNode;
}

function FilterGroup({ label, children }: FilterGroupProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <span style={{ fontSize: 12, color: "#8c8c8c", whiteSpace: "nowrap" }}>{label}</span>
      {children}
    </div>
  );
}
