import { useCallback, useEffect, useMemo, useState } from "react";
import { DatePicker, message, Space, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  getContentTypeLabel,
  getLanguageLabel,
  getPlatformLabel,
  listPosts,
  listWeeklyPostCounts,
  type SnsPost,
  type WeeklyPostCountRow,
} from "../../api/sns";

const WEEKS = [1, 2, 3, 4, 5] as const;

interface TotalsRow {
  account_id: string; // "__total__" sentinel
  isTotal: true;
  week1: number;
  week2: number;
  week3: number;
  week4: number;
  week5: number;
  total: number;
}

type DisplayRow = WeeklyPostCountRow | TotalsRow;

const isTotalRow = (row: DisplayRow): row is TotalsRow =>
  (row as TotalsRow).isTotal === true;

const fmt = (n: number): string => n.toLocaleString("ko-KR");

export default function SnsContentStatus() {
  const [period, setPeriod] = useState<Dayjs>(dayjs());
  const [rows, setRows] = useState<WeeklyPostCountRow[]>([]);
  const [loading, setLoading] = useState(false);

  // 드릴다운: 계정별 게시물 목록 캐시.
  const [postsByAccount, setPostsByAccount] = useState<Record<string, SnsPost[]>>({});
  const [postsLoading, setPostsLoading] = useState<Record<string, boolean>>({});

  const year = period.year();
  const month = period.month() + 1;

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listWeeklyPostCounts({ year, month });
      setRows(res.data);
      setPostsByAccount({});
      setPostsLoading({});
    } catch {
      message.error("콘텐츠 현황 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [year, month]);

  useEffect(() => {
    // year/month 변경 시 집계 fetch (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
  }, [fetchData]);

  // 합계 행 + 일반 행. 합계는 모든 계정의 주차별/전체 게재건수 합.
  const dataSource: DisplayRow[] = useMemo(() => {
    if (rows.length === 0) return [];
    const totals: TotalsRow = {
      account_id: "__total__",
      isTotal: true,
      week1: 0,
      week2: 0,
      week3: 0,
      week4: 0,
      week5: 0,
      total: 0,
    };
    for (const r of rows) {
      totals.week1 += r.week1;
      totals.week2 += r.week2;
      totals.week3 += r.week3;
      totals.week4 += r.week4;
      totals.week5 += r.week5;
      totals.total += r.total;
    }
    return [...rows, totals];
  }, [rows]);

  const loadPosts = useCallback(
    async (accountId: string) => {
      if (postsByAccount[accountId] || postsLoading[accountId]) return;
      setPostsLoading((prev) => ({ ...prev, [accountId]: true }));
      try {
        const dateFrom = period.startOf("month").format("YYYY-MM-DD");
        const dateTo = period.endOf("month").format("YYYY-MM-DD");
        const res = await listPosts({
          account_id: accountId,
          date_from: dateFrom,
          date_to: dateTo,
          limit: 1000,
        });
        setPostsByAccount((prev) => ({ ...prev, [accountId]: res.data }));
      } catch {
        message.error("게시물 조회 실패");
      } finally {
        setPostsLoading((prev) => ({ ...prev, [accountId]: false }));
      }
    },
    [period, postsByAccount, postsLoading],
  );

  const columns: ColumnsType<DisplayRow> = [
    {
      title: "채널",
      width: 320,
      render: (_, row) => {
        if (isTotalRow(row)) {
          return <strong>전체 합계</strong>;
        }
        return (
          <Space size={4} wrap>
            {row.client && <Tag color="purple">{row.client}</Tag>}
            <Tag color="blue">{getPlatformLabel(row.platform)}</Tag>
            <Tag>{getLanguageLabel(row.language)}</Tag>
            <span>{row.handle ?? "-"}</span>
          </Space>
        );
      },
    },
    ...WEEKS.map((week) => ({
      title: `${week}주차`,
      width: 90,
      align: "right" as const,
      render: (_: unknown, row: DisplayRow) => {
        const value = row[`week${week}` as keyof DisplayRow] as number;
        return isTotalRow(row) ? <strong>{fmt(value)}</strong> : fmt(value);
      },
    })),
    {
      title: "합계(월 누적)",
      width: 120,
      align: "right" as const,
      render: (_, row) =>
        isTotalRow(row) ? <strong>{fmt(row.total)}</strong> : <strong>{fmt(row.total)}</strong>,
    },
  ];

  const renderPostsTable = (accountId: string) => {
    const posts = postsByAccount[accountId] ?? [];
    const postColumns: ColumnsType<SnsPost> = [
      {
        title: "제목",
        dataIndex: "title",
        render: (title: string | null) => title ?? "-",
      },
      {
        title: "게재일",
        dataIndex: "posted_at",
        width: 120,
        render: (d: string) => dayjs(d).format("YYYY-MM-DD"),
      },
      {
        title: "형태",
        dataIndex: "content_type",
        width: 100,
        render: (t: string | null) => getContentTypeLabel(t),
      },
      {
        title: "조회수",
        dataIndex: "view_count",
        width: 110,
        align: "right",
        render: (v: number | null) => (v == null ? "-" : fmt(v)),
      },
    ];
    return (
      <Table
        columns={postColumns}
        dataSource={posts}
        rowKey={(p) => p.id}
        loading={postsLoading[accountId]}
        size="small"
        pagination={false}
        locale={{ emptyText: "이번 달 게시물 없음" }}
      />
    );
  };

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>콘텐츠 현황</h2>
        <Space>
          <DatePicker
            picker="month"
            value={period}
            onChange={(v) => v && setPeriod(v)}
            allowClear={false}
            format="YYYY년 M월"
          />
        </Space>
      </div>

      <Table
        columns={columns}
        dataSource={dataSource}
        rowKey={(row) => row.account_id}
        loading={loading}
        size="middle"
        pagination={false}
        expandable={{
          // 합계 행은 펼칠 수 없다 (집계 행).
          rowExpandable: (row) => !isTotalRow(row),
          expandedRowRender: (row) =>
            isTotalRow(row) ? null : renderPostsTable(row.account_id),
          onExpand: (expanded, row) => {
            if (expanded && !isTotalRow(row)) {
              void loadPosts(row.account_id);
            }
          },
        }}
      />
    </div>
  );
}
