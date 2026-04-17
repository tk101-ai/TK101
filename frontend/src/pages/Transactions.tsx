import { useEffect, useState } from "react";
import { Button, DatePicker, Input, message, Modal, Select, Space, Table, Tag, Upload } from "antd";
import { DownloadOutlined, SearchOutlined, SyncOutlined, UploadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { downloadExcel, getTransactions, runMatching, updateMemo, uploadTransactions, type Transaction, type TransactionFilter } from "../api/transactions";
import { getAccounts, type Account } from "../api/accounts";

const { RangePicker } = DatePicker;

export default function Transactions() {
  const [data, setData] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<TransactionFilter>({ limit: 100 });
  const [memoModal, setMemoModal] = useState<{ open: boolean; id: string; memo: string }>({ open: false, id: "", memo: "" });
  const [uploadModal, setUploadModal] = useState(false);
  const [uploadAccountId, setUploadAccountId] = useState<string>("");

  const fetchData = async () => {
    setLoading(true);
    try {
      const [txns, accts] = await Promise.all([getTransactions(filters), getAccounts()]);
      setData(txns.data);
      setAccounts(accts.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const accountMap = new Map(accounts.map((a) => [a.id, a]));

  const handleSearch = () => fetchData();

  const handleDownload = async () => {
    try {
      const res = await downloadExcel(filters);
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = "거래내역_" + dayjs().format("YYYYMMDD") + ".xlsx";
      a.click();
      window.URL.revokeObjectURL(url);
    } catch {
      message.error("다운로드 실패");
    }
  };

  const handleMatch = async () => {
    try {
      const res = await runMatching();
      message.success(res.data.matched_count + "건 매칭 완료");
      fetchData();
    } catch {
      message.error("매칭 실패");
    }
  };

  const handleMemoSave = async () => {
    try {
      await updateMemo(memoModal.id, memoModal.memo);
      message.success("메모 저장 완료");
      setMemoModal({ open: false, id: "", memo: "" });
      fetchData();
    } catch {
      message.error("메모 저장 실패");
    }
  };

  const handleUpload = async (file: File) => {
    if (!uploadAccountId) {
      message.error("계좌를 선택해주세요");
      return false;
    }
    try {
      const res = await uploadTransactions(uploadAccountId, file);
      message.success(res.data.row_count + "건 업로드 완료");
      setUploadModal(false);
      fetchData();
    } catch {
      message.error("업로드 실패");
    }
    return false;
  };

  const columns: ColumnsType<Transaction> = [
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
      render: (id: string) => {
        const acct = accountMap.get(id);
        return acct ? acct.bank_name + " " + acct.account_number.slice(-4) : id.slice(0, 8);
      },
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
      render: (v: string) => Number(v).toLocaleString("ko-KR") + "원",
      sorter: (a, b) => Number(a.amount) - Number(b.amount),
    },
    {
      title: "상대방",
      dataIndex: "counterpart_name",
      width: 150,
    },
    {
      title: "적요",
      dataIndex: "description",
      ellipsis: true,
    },
    {
      title: "매칭",
      dataIndex: "match_status",
      width: 90,
      render: (s: string) => {
        const color = s === "matched" ? "green" : s === "manual" ? "blue" : "default";
        const label = s === "matched" ? "매칭" : s === "manual" ? "수동" : "미매칭";
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: "메모",
      dataIndex: "memo",
      width: 120,
      ellipsis: true,
      render: (memo: string | null, record: Transaction) => (
        <Button
          type="link"
          size="small"
          onClick={() => setMemoModal({ open: true, id: record.id, memo: memo || "" })}
        >
          {memo ? memo.slice(0, 10) + "..." : "메모 추가"}
        </Button>
      ),
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>거래내역</h2>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="계좌 선택"
          allowClear
          style={{ width: 200 }}
          onChange={(v) => setFilters((f) => ({ ...f, account_id: v }))}
          options={accounts.map((a) => ({ label: a.bank_name + " " + a.account_number.slice(-4), value: a.id }))}
        />
        <Select
          placeholder="구분"
          allowClear
          style={{ width: 100 }}
          onChange={(v) => setFilters((f) => ({ ...f, transaction_type: v }))}
          options={[
            { label: "입금", value: "deposit" },
            { label: "출금", value: "withdrawal" },
          ]}
        />
        <Select
          placeholder="매칭상태"
          allowClear
          style={{ width: 120 }}
          onChange={(v) => setFilters((f) => ({ ...f, match_status: v }))}
          options={[
            { label: "미매칭", value: "unmatched" },
            { label: "매칭", value: "matched" },
            { label: "수동", value: "manual" },
          ]}
        />
        <RangePicker
          onChange={(_, dates) =>
            setFilters((f) => ({ ...f, date_from: dates[0] || undefined, date_to: dates[1] || undefined }))
          }
        />
        <Input
          placeholder="검색 (상대방, 적요)"
          prefix={<SearchOutlined />}
          style={{ width: 200 }}
          onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
          onPressEnter={handleSearch}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          조회
        </Button>
      </Space>

      <Space style={{ marginBottom: 16, float: "right" }}>
        <Button icon={<UploadOutlined />} onClick={() => setUploadModal(true)}>
          엑셀 업로드
        </Button>
        <Button icon={<SyncOutlined />} onClick={handleMatch}>
          자동 매칭
        </Button>
        <Button icon={<DownloadOutlined />} onClick={handleDownload}>
          엑셀 다운로드
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (t) => "총 " + t + "건" }}
        scroll={{ x: 1100 }}
      />

      <Modal
        title="메모 수정"
        open={memoModal.open}
        onOk={handleMemoSave}
        onCancel={() => setMemoModal({ open: false, id: "", memo: "" })}
        okText="저장"
        cancelText="취소"
      >
        <Input.TextArea
          rows={4}
          value={memoModal.memo}
          onChange={(e) => setMemoModal((m) => ({ ...m, memo: e.target.value }))}
          placeholder="특이사항이나 메모를 입력하세요"
        />
      </Modal>

      <Modal
        title="거래내역 엑셀 업로드"
        open={uploadModal}
        onCancel={() => setUploadModal(false)}
        footer={null}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select
            placeholder="업로드할 계좌 선택"
            style={{ width: "100%" }}
            onChange={setUploadAccountId}
            options={accounts.map((a) => ({ label: a.bank_name + " " + a.account_number, value: a.id }))}
          />
          <Upload.Dragger
            accept=".xlsx,.xls"
            showUploadList={false}
            beforeUpload={handleUpload}
          >
            <p>엑셀 파일을 드래그하거나 클릭하여 업로드</p>
          </Upload.Dragger>
        </Space>
      </Modal>
    </div>
  );
}
