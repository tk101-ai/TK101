import { Card, Col, Row, Statistic } from "antd";
import { BankOutlined, SwapOutlined, FileTextOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";
import { getAccounts } from "../api/accounts";
import { getTransactions } from "../api/transactions";

export default function Dashboard() {
  const [accountCount, setAccountCount] = useState(0);
  const [txnCount, setTxnCount] = useState(0);
  const [unmatchedCount, setUnmatchedCount] = useState(0);

  useEffect(() => {
    getAccounts().then((res) => setAccountCount(res.data.length));
    getTransactions({ limit: 1 }).then((res) => {
      setTxnCount(res.data.length > 0 ? res.data.length : 0);
    });
    getTransactions({ match_status: "unmatched", limit: 1000 }).then((res) => {
      setUnmatchedCount(res.data.length);
    });
  }, []);

  return (
    <div>
      <h2 style={{ marginBottom: 24 }}>대시보드</h2>
      <Row gutter={16}>
        <Col span={8}>
          <Card>
            <Statistic title="등록 계좌" value={accountCount} prefix={<BankOutlined />} suffix="개" />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="총 거래내역" value={txnCount} prefix={<SwapOutlined />} suffix="건" />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="미매칭 거래" value={unmatchedCount} prefix={<FileTextOutlined />} valueStyle={{ color: unmatchedCount > 0 ? "#cf1322" : "#3f8600" }} suffix="건" />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
