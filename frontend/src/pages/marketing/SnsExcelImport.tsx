import { useState } from "react";
import { Alert, Button, Card, Col, message, Result, Row, Space, Spin, Typography, Upload } from "antd";
import { CloudUploadOutlined, InboxOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { importMarketing1Excel, type SnsImportResponse } from "../../api/sns";

const { Paragraph, Text } = Typography;

export default function SnsExcelImport() {
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<SnsImportResponse | null>(null);

  const handleImport = async () => {
    const file = fileList[0]?.originFileObj as File | undefined;
    if (!file) {
      message.error("파일을 선택하세요");
      return;
    }
    setImporting(true);
    setResult(null);
    try {
      const res = await importMarketing1Excel(file);
      setResult(res.data);
      message.success("가져오기 완료");
    } catch {
      message.error("가져오기 실패");
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setFileList([]);
    setResult(null);
  };

  return (
    <div style={{ maxWidth: 1200 }}>
      <h2 style={{ marginBottom: 28, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
        엑셀 가져오기
      </h2>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="마케팅1팀 SNS 통합 엑셀"
        description={
          <Paragraph style={{ margin: 0 }}>
            <Text code>[TK내부] 2026 서울시 글로벌 SNS DB 관리.xlsx</Text> 형식의 파일을 업로드하면
            계정, 주간 팔로워, 콘텐츠 데이터가 일괄 적재됩니다.
          </Paragraph>
        }
      />

      <Spin spinning={importing} tip="가져오는 중...">
        <Upload.Dragger
          accept=".xlsx,.xls"
          fileList={fileList}
          beforeUpload={(file) => {
            setFileList([
              {
                uid: file.uid,
                name: file.name,
                status: "done",
                originFileObj: file,
              } as UploadFile,
            ]);
            setResult(null);
            return false;
          }}
          onRemove={() => {
            setFileList([]);
            setResult(null);
          }}
          maxCount={1}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">엑셀 파일을 드래그하거나 클릭하여 선택하세요</p>
          <p className="ant-upload-hint">.xlsx, .xls 형식의 단일 파일만 지원합니다</p>
        </Upload.Dragger>

        <Space style={{ marginTop: 16 }}>
          <Button
            type="primary"
            icon={<CloudUploadOutlined />}
            disabled={fileList.length === 0 || importing}
            onClick={handleImport}
          >
            가져오기
          </Button>
          <Button onClick={handleReset} disabled={importing}>
            초기화
          </Button>
        </Space>
      </Spin>

      {result && (
        <div style={{ marginTop: 32 }}>
          <Result status="success" title="가져오기가 완료되었습니다" />
          <Row gutter={16}>
            <Col xs={12} md={6}>
              <Card>
                <Text type="secondary">신규 계정</Text>
                <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
                  {result.accounts_added.toLocaleString("ko-KR")}
                </div>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Text type="secondary">신규 주간 팔로워</Text>
                <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
                  {result.snapshots_added.toLocaleString("ko-KR")}
                </div>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Text type="secondary">신규 콘텐츠</Text>
                <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
                  {result.posts_added.toLocaleString("ko-KR")}
                </div>
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card>
                <Text type="secondary">갱신 콘텐츠</Text>
                <div style={{ fontSize: 28, fontWeight: 700, marginTop: 8 }}>
                  {result.posts_updated.toLocaleString("ko-KR")}
                </div>
              </Card>
            </Col>
          </Row>
        </div>
      )}
    </div>
  );
}
