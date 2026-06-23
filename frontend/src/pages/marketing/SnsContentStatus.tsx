import { useCallback, useEffect, useMemo, useState } from "react";
import { Button, DatePicker, message, Select, Space, Table, Tag } from "antd";
import { DownloadOutlined, FileExcelOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  POST_CATEGORIES,
  POST_CATEGORY_COLORS,
  exportBrandWorkbook,
  exportContentStatus,
  getContentTypeLabel,
  getLanguageLabel,
  getPlatformLabel,
  listAccounts,
  listPosts,
  listWeeklyPostCounts,
  type PostCategory,
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

  // 구분(카테고리)별 게시물 수 — 선택한 월의 전체 게시물 기준. "미분류" 별도 집계.
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({});
  const [uncategorizedCount, setUncategorizedCount] = useState(0);

  // 드릴다운: 계정별 게시물 목록 캐시.
  const [postsByAccount, setPostsByAccount] = useState<Record<string, SnsPost[]>>({});
  const [postsLoading, setPostsLoading] = useState<Record<string, boolean>>({});
  const [exporting, setExporting] = useState(false);

  // 통합 워크북 내보내기 — 브랜드(client) 선택. 옵션은 계정 목록의 distinct client.
  const [brands, setBrands] = useState<string[]>([]);
  const [selectedBrand, setSelectedBrand] = useState<string | undefined>(undefined);
  const [exportingBook, setExportingBook] = useState(false);

  const year = period.year();
  const month = period.month() + 1;

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      await exportContentStatus({ year, month });
    } catch {
      message.error("엑셀 내보내기 실패");
    } finally {
      setExporting(false);
    }
  }, [year, month]);

  // 브랜드 목록(distinct client) 로드 — 한 번만. 단일 브랜드여도 동작.
  useEffect(() => {
    void (async () => {
      try {
        const res = await listAccounts();
        const distinct = Array.from(
          new Set(
            res.data
              .map((a) => a.client)
              .filter((c): c is string => Boolean(c)),
          ),
        ).sort();
        setBrands(distinct);
        // eslint-disable-next-line react-hooks/set-state-in-effect
        if (distinct.length > 0) setSelectedBrand((prev) => prev ?? distinct[0]);
      } catch {
        // 브랜드 로드 실패는 통합 내보내기만 비활성화 — 페이지 본 기능은 영향 없음.
      }
    })();
  }, []);

  const handleExportWorkbook = useCallback(async () => {
    if (!selectedBrand) {
      message.warning("브랜드를 선택하세요");
      return;
    }
    setExportingBook(true);
    try {
      await exportBrandWorkbook({ client: selectedBrand, year, month });
    } catch {
      message.error("통합 워크북 내보내기 실패");
    } finally {
      setExportingBook(false);
    }
  }, [selectedBrand, year, month]);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const dateFrom = period.startOf("month").format("YYYY-MM-DD");
      const dateTo = period.endOf("month").format("YYYY-MM-DD");
      const [countsRes, postsRes] = await Promise.all([
        listWeeklyPostCounts({ year, month }),
        // 구분별 집계용 — 해당 월 전체 게시물(계정 무관). limit 상한껏.
        listPosts({ date_from: dateFrom, date_to: dateTo, limit: 1000 }),
      ]);
      setRows(countsRes.data);
      setPostsByAccount({});
      setPostsLoading({});

      const counts: Record<string, number> = {};
      let uncategorized = 0;
      for (const p of postsRes.data) {
        if (p.category) counts[p.category] = (counts[p.category] ?? 0) + 1;
        else uncategorized += 1;
      }
      setCategoryCounts(counts);
      setUncategorizedCount(uncategorized);
    } catch {
      message.error("콘텐츠 현황 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [year, month, period]);

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
        title: "구분",
        dataIndex: "category",
        width: 90,
        render: (c: PostCategory | null) =>
          c ? (
            <Tag color={POST_CATEGORY_COLORS[c]} style={{ margin: 0 }}>
              {c}
            </Tag>
          ) : (
            "-"
          ),
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
          <Button
            icon={<DownloadOutlined />}
            loading={exporting}
            disabled={rows.length === 0}
            onClick={handleExport}
          >
            엑셀 내보내기
          </Button>
        </Space>
      </div>

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 20,
          padding: "10px 14px",
          background: "#fafafa",
          border: "1px solid #f0f0f0",
          borderRadius: 8,
        }}
      >
        <FileExcelOutlined style={{ color: "#52796f" }} />
        <span style={{ fontWeight: 600, fontSize: 13 }}>통합 워크북 내보내기</span>
        <Select
          placeholder="브랜드 선택"
          value={selectedBrand}
          onChange={setSelectedBrand}
          options={brands.map((b) => ({ value: b, label: b }))}
          style={{ minWidth: 140 }}
          size="small"
          disabled={brands.length === 0}
        />
        <span style={{ color: "#8c8c8c", fontSize: 12 }}>
          {period.format("YYYY년 M월")} (월간요약 + 채널별 콘텐츠 + 팔로워)
        </span>
        <Button
          type="primary"
          ghost
          size="small"
          icon={<DownloadOutlined />}
          loading={exportingBook}
          disabled={!selectedBrand}
          onClick={handleExportWorkbook}
        >
          다운로드
        </Button>
      </div>

      {/* 구분(카테고리)별 게시물 수 — 선택한 월 기준. SeoulSns 에서 수동 태그한 값을 집계. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: 8,
          marginBottom: 20,
          padding: "10px 14px",
          background: "#fafafa",
          border: "1px solid #f0f0f0",
          borderRadius: 8,
        }}
      >
        <span style={{ fontWeight: 600, fontSize: 13, marginRight: 4 }}>구분별 집계</span>
        {(POST_CATEGORIES as readonly PostCategory[]).map((cat) => (
          <Tag key={cat} color={POST_CATEGORY_COLORS[cat]} style={{ margin: 0 }}>
            {cat} {fmt(categoryCounts[cat] ?? 0)}
          </Tag>
        ))}
        <Tag style={{ margin: 0 }}>미분류 {fmt(uncategorizedCount)}</Tag>
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
