import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Empty,
  Modal,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  applyMatch,
  getMatchCandidates,
  type Transaction,
} from "../../api/transactions";
import type { Account } from "../../api/accounts";
import { extractErrorDetail } from "../../utils/errorUtils";

interface MatchingCandidatesModalProps {
  open: boolean;
  source: Transaction | null;
  accounts: Account[];
  onClose: () => void;
  onMatched: () => void;
}

function formatAmount(v: string): string {
  return `${Number(v).toLocaleString("ko-KR")}원`;
}

export default function MatchingCandidatesModal({
  open,
  source,
  accounts,
  onClose,
  onMatched,
}: MatchingCandidatesModalProps) {
  const [candidates, setCandidates] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState<string | null>(null);

  const accountLabel = useCallback(
    (id: string) => {
      const acct = accounts.find((a) => a.id === id);
      return acct
        ? `${acct.bank_name} ${acct.account_number.slice(-4)}`
        : id.slice(0, 8);
    },
    [accounts],
  );

  const reload = useCallback(async () => {
    if (!source) return;
    setLoading(true);
    try {
      const data = await getMatchCandidates(source.id, 7);
      setCandidates(data);
    } catch (err) {
      message.error(extractErrorDetail(err, "매칭 후보를 불러오지 못했습니다"));
    } finally {
      setLoading(false);
    }
  }, [source]);

  useEffect(() => {
    if (open && source) {
      // 모달 open + source 변경 시 매칭 후보 비동기 로드 (의도된 패턴).
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void reload();
    } else {
      setCandidates([]);
    }
  }, [open, source, reload]);

  const handleApply = async (candidate: Transaction) => {
    if (!source) return;
    setApplying(candidate.id);
    try {
      await applyMatch(source.id, candidate.id);
      message.success("매칭 완료");
      onMatched();
      onClose();
    } catch (err) {
      message.error(extractErrorDetail(err, "매칭 실패"));
    } finally {
      setApplying(null);
    }
  };

  const columns: ColumnsType<Transaction> = [
    { title: "거래일", dataIndex: "transaction_date", width: 110 },
    {
      title: "계좌",
      dataIndex: "account_id",
      width: 160,
      render: (id: string) => accountLabel(id),
    },
    {
      title: "구분",
      dataIndex: "transaction_type",
      width: 80,
      render: (t: string) => (
        <Tag color={t === "deposit" ? "green" : "red"}>
          {t === "deposit" ? "입금" : "출금"}
        </Tag>
      ),
    },
    {
      title: "금액",
      dataIndex: "amount",
      align: "right",
      width: 130,
      render: (v: string) => formatAmount(v),
    },
    { title: "거래처", dataIndex: "counterpart_name", ellipsis: true },
    {
      title: "작업",
      key: "action",
      width: 110,
      render: (_: unknown, record: Transaction) => (
        <Button
          type="primary"
          size="small"
          loading={applying === record.id}
          onClick={() => handleApply(record)}
        >
          매칭
        </Button>
      ),
    },
  ];

  return (
    <Modal
      title="매칭 후보"
      open={open}
      onCancel={onClose}
      footer={null}
      width={820}
      destroyOnClose
    >
      {source && (
        <Typography.Paragraph type="secondary">
          기준 거래: {source.transaction_date} ·{" "}
          <Tag color={source.transaction_type === "deposit" ? "green" : "red"}>
            {source.transaction_type === "deposit" ? "입금" : "출금"}
          </Tag>{" "}
          {formatAmount(source.amount)} · {source.counterpart_name ?? "-"}
        </Typography.Paragraph>
      )}
      <Spin spinning={loading}>
        {candidates.length === 0 ? (
          <Empty description="7일 윈도우 내 매칭 후보가 없습니다" />
        ) : (
          <Table
            columns={columns}
            dataSource={candidates}
            rowKey="id"
            size="small"
            pagination={false}
          />
        )}
      </Spin>
    </Modal>
  );
}
