import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, DatePicker, InputNumber, message, Space, Table, Tag } from "antd";
import { SaveOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  bulkUpsertSnapshots,
  getLanguageLabel,
  getPlatformLabel,
  listAccounts,
  listSnapshots,
  type SnsAccount,
  type SnsSnapshot,
  type UpsertSnapshotRequest,
} from "../../api/sns";

interface SnapshotRow {
  account: SnsAccount;
  weeks: Record<number, number | null>;
}

const WEEKS = [1, 2, 3, 4] as const;

export default function SnsWeeklySnapshots() {
  const [period, setPeriod] = useState<Dayjs>(dayjs());
  const [accounts, setAccounts] = useState<SnsAccount[]>([]);
  const [snapshots, setSnapshots] = useState<SnsSnapshot[]>([]);
  const [edits, setEdits] = useState<Record<string, Record<number, number | null>>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const year = period.year();
  const month = period.month() + 1;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [accRes, snapRes] = await Promise.all([
        listAccounts(),
        listSnapshots({ year, month }),
      ]);
      setAccounts(accRes.data.filter((a) => a.is_active));
      setSnapshots(snapRes.data);
      setEdits({});
    } catch {
      message.error("데이터 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const rows: SnapshotRow[] = useMemo(() => {
    return accounts.map((account) => {
      const weeks: Record<number, number | null> = { 1: null, 2: null, 3: null, 4: null };
      for (const snap of snapshots) {
        if (snap.account_id === account.id && WEEKS.includes(snap.week_number as 1 | 2 | 3 | 4)) {
          weeks[snap.week_number] = snap.followers;
        }
      }
      return { account, weeks };
    });
  }, [accounts, snapshots]);

  const getCellValue = (accountId: string, weekNumber: number, baseValue: number | null): number | null => {
    const overrides = edits[accountId];
    if (overrides && weekNumber in overrides) {
      return overrides[weekNumber];
    }
    return baseValue;
  };

  const handleCellChange = (accountId: string, weekNumber: number, value: number | null) => {
    setEdits((prev) => ({
      ...prev,
      [accountId]: { ...(prev[accountId] ?? {}), [weekNumber]: value },
    }));
  };

  const handleSave = async () => {
    const payload: UpsertSnapshotRequest[] = [];
    for (const [accountId, weekMap] of Object.entries(edits)) {
      for (const [weekStr, followers] of Object.entries(weekMap)) {
        if (followers == null) continue;
        payload.push({
          account_id: accountId,
          year,
          month,
          week_number: Number(weekStr),
          followers,
        });
      }
    }
    if (payload.length === 0) {
      message.info("저장할 변경 사항이 없습니다");
      return;
    }
    setSaving(true);
    try {
      await bulkUpsertSnapshots(payload);
      message.success(payload.length + "건 저장 완료");
      fetchData();
    } catch {
      message.error("저장 실패");
    } finally {
      setSaving(false);
    }
  };

  const columns: ColumnsType<SnapshotRow> = [
    {
      title: "어권",
      width: 90,
      render: (_, row) => <Tag>{getLanguageLabel(row.account.language)}</Tag>,
    },
    {
      title: "플랫폼",
      width: 110,
      render: (_, row) => <Tag color="blue">{getPlatformLabel(row.account.platform)}</Tag>,
    },
    {
      title: "핸들",
      width: 200,
      render: (_, row) => row.account.handle ?? row.account.external_id ?? "-",
    },
    ...WEEKS.map((week) => ({
      title: `${week}주차`,
      width: 140,
      align: "right" as const,
      render: (_: unknown, row: SnapshotRow) => {
        const value = getCellValue(row.account.id, week, row.weeks[week]);
        return (
          <InputNumber
            min={0}
            value={value ?? undefined}
            placeholder="-"
            style={{ width: "100%" }}
            onChange={(v) => handleCellChange(row.account.id, week, typeof v === "number" ? v : null)}
            formatter={(v) => (v == null ? "" : Number(v).toLocaleString("ko-KR"))}
            parser={(v) => (v ? Number(v.replace(/,/g, "")) : 0)}
          />
        );
      },
    })),
  ];

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>주간 팔로워</h2>
        <Space>
          <DatePicker
            picker="month"
            value={period}
            onChange={(v) => v && setPeriod(v)}
            allowClear={false}
            format="YYYY년 M월"
          />
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            저장
          </Button>
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={rows}
        rowKey={(row) => row.account.id}
        loading={loading}
        size="middle"
        pagination={false}
      />
    </div>
  );
}
