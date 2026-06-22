import { Button, Popconfirm, Space, Tag, Tooltip, Typography } from "antd";
import {
  DeleteOutlined,
  LinkOutlined,
  PaperClipOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { type Transaction, type TransactionUpdate } from "../../../api/transactions";
import { type CategoryRead } from "../../../api/categories";
import { type Account } from "../../../api/accounts";
import { formatAmount } from "./format";
import { CategoryCell } from "./CategoryCell";
import { MemoCell } from "./MemoCell";

// ---------------------------------------------------------------------------
// 컬럼 정의
// ---------------------------------------------------------------------------

interface BuildColumnsArgs {
  accountMap: Map<string, Account>;
  categories: CategoryRead[];
  patchTransaction: (
    id: string,
    body: TransactionUpdate,
    successMsg?: string,
  ) => Promise<void>;
  isAdmin: boolean;
  onRestore: (id: string) => void;
  onAttachment: (id: string) => void;
  onMatch: (record: Transaction) => void;
  onRemoveMatch: (id: string) => void;
  onDelete: (id: string) => void;
}

export function buildTransactionColumns({
  accountMap,
  categories,
  patchTransaction,
  isAdmin,
  onRestore,
  onAttachment,
  onMatch,
  onRemoveMatch,
  onDelete,
}: BuildColumnsArgs): ColumnsType<Transaction> {
  const accountRender = (id: string) => {
    const acct = accountMap.get(id);
    return acct ? `${acct.bank_name} ${acct.account_number.slice(-4)}` : id.slice(0, 8);
  };

  return [
    {
      title: "거래일",
      dataIndex: "transaction_date",
      width: 110,
      sorter: (a, b) => a.transaction_date.localeCompare(b.transaction_date),
    },
    {
      title: "계좌",
      dataIndex: "account_id",
      width: 150,
      render: (id: string) => accountRender(id),
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
      width: 130,
      align: "right" as const,
      render: (v: string) => formatAmount(v),
      sorter: (a, b) => Number(a.amount) - Number(b.amount),
    },
    {
      title: "잔액",
      dataIndex: "balance",
      width: 130,
      align: "right" as const,
      render: (v: string | null) => formatAmount(v),
    },
    {
      title: "거래처",
      dataIndex: "counterpart_name",
      width: 150,
      ellipsis: true,
    },
    {
      title: "적요",
      dataIndex: "description",
      ellipsis: true,
    },
    {
      title: "카테고리",
      dataIndex: "category_id",
      width: 160,
      render: (_: unknown, record: Transaction) => (
        <CategoryCell
          value={record.category_id ?? null}
          categories={categories}
          onChange={(categoryId) =>
            patchTransaction(record.id, { category_id: categoryId }, "카테고리 저장")
          }
        />
      ),
    },
    {
      title: "메모",
      dataIndex: "memo",
      width: 140,
      ellipsis: true,
      render: (_: unknown, record: Transaction) => (
        <MemoCell
          key={record.memo ?? "__empty__"}
          value={record.memo}
          onSave={(memo) => patchTransaction(record.id, { memo }, "메모 저장")}
        />
      ),
    },
    {
      title: "태그",
      dataIndex: "tags",
      width: 160,
      render: (tags: string[] | null) =>
        tags && tags.length > 0 ? (
          <Space size={4} wrap>
            {tags.map((t) => (
              <Tag key={t}>{t}</Tag>
            ))}
          </Space>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: "첨부",
      dataIndex: "attachment_url",
      width: 70,
      align: "center" as const,
      render: (url: string | null | undefined) =>
        url ? (
          <Tooltip title="첨부 있음">
            <PaperClipOutlined style={{ color: "#1677ff" }} />
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">-</Typography.Text>
        ),
    },
    {
      title: "매칭",
      dataIndex: "match_status",
      width: 130,
      render: (_: unknown, record: Transaction) => {
        const s = record.match_status;
        const color = s === "matched" ? "green" : s === "manual" ? "blue" : "default";
        const label = s === "matched" ? "매칭" : s === "manual" ? "수동" : "미매칭";
        const matchedAccount = record.matched_transaction_id
          ? "(쌍 있음)"
          : "";
        return (
          <Space size={4}>
            <Tag color={color}>{label}</Tag>
            {matchedAccount && (
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                {matchedAccount}
              </Typography.Text>
            )}
          </Space>
        );
      },
    },
    {
      title: "액션",
      key: "action",
      width: 200,
      fixed: "right" as const,
      render: (_: unknown, record: Transaction) => {
        if (record.is_deleted) {
          return isAdmin ? (
            <Button
              size="small"
              icon={<UndoOutlined />}
              onClick={() => onRestore(record.id)}
            >
              복원
            </Button>
          ) : (
            <Tag>삭제됨</Tag>
          );
        }
        return (
          <Space size={4}>
            <Tooltip title="영수증 / 첨부">
              <Button
                size="small"
                type="text"
                icon={<PaperClipOutlined />}
                onClick={() => onAttachment(record.id)}
              />
            </Tooltip>
            {record.match_status === "unmatched" ? (
              <Tooltip title="매칭 후보">
                <Button
                  size="small"
                  type="text"
                  icon={<LinkOutlined />}
                  onClick={() => onMatch(record)}
                />
              </Tooltip>
            ) : (
              <Tooltip title="매칭 해제">
                <Popconfirm
                  title="매칭 해제"
                  onConfirm={() => onRemoveMatch(record.id)}
                  okText="해제"
                  cancelText="취소"
                >
                  <Button size="small" type="text" icon={<LinkOutlined />} danger />
                </Popconfirm>
              </Tooltip>
            )}
            {isAdmin && (
              <Popconfirm
                title="거래 삭제"
                description="이 거래를 비활성 처리할까요?"
                okText="삭제"
                cancelText="취소"
                onConfirm={() => onDelete(record.id)}
              >
                <Button size="small" type="text" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];
}
