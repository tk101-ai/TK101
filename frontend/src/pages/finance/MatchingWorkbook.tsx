import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Input,
  List,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
  message,
} from "antd";
import { LinkOutlined, ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import dayjs, { type Dayjs } from "dayjs";
import {
  applyMatch,
  getMatchCandidates,
  listTransactions,
  type Transaction,
} from "../../api/transactions";
import { listAccounts, type Account } from "../../api/accounts";
import { makeErrorExtractor } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

const extractErrorDetail = makeErrorExtractor({ useAxiosMessage: true });

function formatAmount(amount: string | number, type: string): string {
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  const sign = type === "deposit" ? "+" : "-";
  const formatted = Math.abs(num).toLocaleString("ko-KR");
  return `${sign}${formatted}`;
}

function amountColor(type: string): string {
  return type === "deposit" ? "#52c41a" : "#f5222d";
}

interface FilterState {
  accountId?: string;
  dateRange: [Dayjs, Dayjs] | null;
  search: string;
}

export default function MatchingWorkbook() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [list, setList] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [loadingList, setLoadingList] = useState(false);
  const [selected, setSelected] = useState<Transaction | null>(null);
  const [candidates, setCandidates] = useState<Transaction[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(false);
  const [matching, setMatching] = useState<string | null>(null);

  const [filters, setFilters] = useState<FilterState>({
    accountId: undefined,
    dateRange: null,
    search: "",
  });
  const [searchInput, setSearchInput] = useState("");

  // 계좌 목록 1회 로드
  useEffect(() => {
    const run = async () => {
      try {
        const accs = await listAccounts();
        setAccounts(accs);
      } catch (err: unknown) {
        message.warning(extractErrorDetail(err, "계좌 목록 로딩 실패"));
      }
    };
    void run();
  }, []);

  const fetchUnmatched = useCallback(async () => {
    setLoadingList(true);
    try {
      const res = await listTransactions({
        match_status: "unmatched",
        account_id: filters.accountId,
        date_from: filters.dateRange?.[0]?.format("YYYY-MM-DD"),
        date_to: filters.dateRange?.[1]?.format("YYYY-MM-DD"),
        keyword: filters.search || undefined,
        limit: 200,
        offset: 0,
      });
      setList(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "미매칭 거래 조회 실패"));
    } finally {
      setLoadingList(false);
    }
  }, [filters]);

  useEffect(() => {
    const run = async () => {
      await fetchUnmatched();
    };
    void run();
  }, [fetchUnmatched]);

  const fetchCandidates = useCallback(async (tx: Transaction) => {
    setLoadingCandidates(true);
    setCandidates([]);
    try {
      const items = await getMatchCandidates(tx.id, 7);
      setCandidates(items);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "후보 조회 실패"));
    } finally {
      setLoadingCandidates(false);
    }
  }, []);

  const handleSelect = (tx: Transaction) => {
    setSelected(tx);
    void fetchCandidates(tx);
  };

  const handleMatch = async (candidate: Transaction) => {
    if (!selected) return;
    setMatching(candidate.id);
    try {
      await applyMatch(selected.id, candidate.id);
      message.success("매칭되었습니다");
      // 좌측 목록에서 두 거래 모두 제거
      setList((prev) =>
        prev.filter((t) => t.id !== selected.id && t.id !== candidate.id),
      );
      setSelected(null);
      setCandidates([]);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "매칭 실패"));
    } finally {
      setMatching(null);
    }
  };

  const stats = useMemo(() => {
    const deposits = list.filter((t) => t.transaction_type === "deposit").length;
    const withdrawals = list.filter((t) => t.transaction_type === "withdrawal").length;
    return { deposits, withdrawals };
  }, [list]);

  const accountOptions = useMemo(
    () =>
      accounts.map((a) => ({
        value: a.id,
        label: `${a.bank_name} · ${a.account_number}`,
      })),
    [accounts],
  );

  const accountLabel = useCallback(
    (id: string) => {
      const a = accounts.find((x) => x.id === id);
      return a ? `${a.bank_name} ${a.account_number.slice(-4)}` : id.slice(0, 6);
    },
    [accounts],
  );

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          매칭 워크북
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          미매칭 거래를 좌측에서 선택해 우측 후보 중 짝을 골라 수동으로 매칭합니다.
        </Paragraph>
      </div>

      <Space size={16} wrap style={{ marginBottom: 16 }}>
        <Statistic title="미매칭 합계" value={total} suffix="건" />
        <Statistic
          title="입금"
          value={stats.deposits}
          suffix="건"
          valueStyle={{ color: "#52c41a" }}
        />
        <Statistic
          title="출금"
          value={stats.withdrawals}
          suffix="건"
          valueStyle={{ color: "#f5222d" }}
        />
      </Space>

      <Card size="small" style={{ marginBottom: 16 }}>
        <Space wrap>
          <Select
            placeholder="계좌"
            allowClear
            style={{ width: 240 }}
            options={accountOptions}
            value={filters.accountId}
            onChange={(v) => setFilters((s) => ({ ...s, accountId: v }))}
          />
          <RangePicker
            value={filters.dateRange ?? undefined}
            onChange={(v) =>
              setFilters((s) => ({
                ...s,
                dateRange: v && v[0] && v[1] ? [v[0], v[1]] : null,
              }))
            }
          />
          <Input
            placeholder="거래처/메모 검색"
            prefix={<SearchOutlined />}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onPressEnter={() => setFilters((s) => ({ ...s, search: searchInput }))}
            style={{ width: 220 }}
            allowClear
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setFilters((s) => ({ ...s, search: searchInput }));
              void fetchUnmatched();
            }}
          >
            새로고침
          </Button>
        </Space>
      </Card>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "1fr 1fr" }}>
        {/* 좌측: 미매칭 거래 */}
        <Card
          size="small"
          title={`미매칭 거래 (${list.length}/${total})`}
          styles={{ body: { padding: 0, maxHeight: 600, overflow: "auto" } }}
        >
          <Spin spinning={loadingList}>
            {list.length === 0 ? (
              <Empty description="미매칭 거래가 없습니다" style={{ padding: 24 }} />
            ) : (
              <List
                size="small"
                dataSource={list}
                renderItem={(tx) => {
                  const isActive = selected?.id === tx.id;
                  return (
                    <List.Item
                      onClick={() => handleSelect(tx)}
                      style={{
                        cursor: "pointer",
                        background: isActive ? "#e6f4ff" : undefined,
                        paddingInline: 12,
                      }}
                    >
                      <div style={{ width: "100%" }}>
                        <Space size={6} style={{ width: "100%", justifyContent: "space-between" }}>
                          <Space size={6}>
                            <Tag
                              color={tx.transaction_type === "deposit" ? "green" : "red"}
                              style={{ marginRight: 0 }}
                            >
                              {tx.transaction_type === "deposit" ? "입금" : "출금"}
                            </Tag>
                            <Text strong>{tx.counterpart_name || "-"}</Text>
                          </Space>
                          <Text
                            strong
                            style={{ color: amountColor(tx.transaction_type) }}
                          >
                            {formatAmount(tx.amount, tx.transaction_type)}
                          </Text>
                        </Space>
                        <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                          {dayjs(tx.transaction_date).format("YYYY-MM-DD")} ·
                          {" "}계좌 {accountLabel(tx.account_id)}
                          {tx.description ? ` · ${tx.description.slice(0, 30)}` : ""}
                        </div>
                      </div>
                    </List.Item>
                  );
                }}
              />
            )}
          </Spin>
        </Card>

        {/* 우측: 후보 */}
        <Card
          size="small"
          title={
            selected
              ? `매칭 후보 — ${dayjs(selected.transaction_date).format("MM-DD")} ${formatAmount(selected.amount, selected.transaction_type)} ${selected.counterpart_name ?? ""}`
              : "거래를 선택하세요"
          }
          styles={{ body: { padding: 0, maxHeight: 600, overflow: "auto" } }}
        >
          <Spin spinning={loadingCandidates}>
            {!selected ? (
              <Empty description="좌측에서 거래를 클릭하세요" style={{ padding: 24 }} />
            ) : candidates.length === 0 && !loadingCandidates ? (
              <Empty description="후보가 없습니다 (±7일)" style={{ padding: 24 }} />
            ) : (
              <List
                size="small"
                dataSource={candidates}
                renderItem={(c) => (
                  <List.Item
                    style={{ paddingInline: 12 }}
                    actions={[
                      <Button
                        key="match"
                        type="primary"
                        size="small"
                        icon={<LinkOutlined />}
                        loading={matching === c.id}
                        onClick={() => handleMatch(c)}
                      >
                        매칭
                      </Button>,
                    ]}
                  >
                    <div style={{ flex: 1 }}>
                      <Space size={6}>
                        <Tag
                          color={c.transaction_type === "deposit" ? "green" : "red"}
                          style={{ marginRight: 0 }}
                        >
                          {c.transaction_type === "deposit" ? "입금" : "출금"}
                        </Tag>
                        <Text strong>{c.counterpart_name || "-"}</Text>
                        <Text strong style={{ color: amountColor(c.transaction_type) }}>
                          {formatAmount(c.amount, c.transaction_type)}
                        </Text>
                      </Space>
                      <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
                        {dayjs(c.transaction_date).format("YYYY-MM-DD")} · 계좌 {accountLabel(c.account_id)}
                        {c.description ? ` · ${c.description.slice(0, 30)}` : ""}
                      </div>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </Spin>
        </Card>
      </div>
    </div>
  );
}
