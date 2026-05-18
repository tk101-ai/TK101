import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Space,
  Spin,
  Typography,
  Upload,
  message,
} from "antd";
import {
  CloudUploadOutlined,
  GoldOutlined,
  InboxOutlined,
  TableOutlined,
} from "@ant-design/icons";
import type { UploadProps } from "antd";
import { Link } from "react-router-dom";
import {
  uploadDistributionData,
  type DataUploadResult,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { Dragger } = Upload;

/**
 * 신사업유통 데이터 업로드 페이지 (T9 Phase B-1).
 *
 * 래더엑스 종합관리시트 + 명품재고대장이 포함된 엑셀(.xlsx/.xlsm)을 업로드한다.
 * - 동일 주차는 자동 갱신 (upsert)
 * - 명품재고는 매주 전체 갱신 (wipe & insert)
 *
 * 백엔드: `POST /api/distribution/data/upload` (multipart/form-data)
 */
export default function DataUploadPage() {
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<DataUploadResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // 자동 업로드 차단 — 사용자가 "업로드 시작" 버튼을 누를 때만 처리.
  const uploadProps: UploadProps = {
    accept: ".xlsx,.xlsm",
    multiple: false,
    showUploadList: false,
    beforeUpload: (file) => {
      setPendingFile(file);
      setResult(null);
      setErrorMsg(null);
      return false;
    },
  };

  const handleUpload = async () => {
    if (!pendingFile) {
      message.warning("업로드할 파일을 먼저 선택하세요");
      return;
    }
    setUploading(true);
    setErrorMsg(null);
    try {
      const res = await uploadDistributionData(pendingFile);
      setResult(res);
      message.success("업로드 완료");
    } catch (err: unknown) {
      const detail = extractErrorDetail(err, "업로드 실패", {
        useAxiosMessage: true,
      });
      setErrorMsg(detail);
      message.error(detail);
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setPendingFile(null);
    setResult(null);
    setErrorMsg(null);
  };

  return (
    <div style={{ maxWidth: 960 }}>
      <div
        style={{
          marginBottom: 24,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
            신사업유통 데이터 업로드
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            래더엑스 종합관리시트 + 명품재고대장이 포함된 엑셀 파일을 업로드하세요.
            동일 주차는 자동 갱신, 명품재고는 매주 전체 갱신됩니다.
          </Paragraph>
        </div>
        <Space>
          <Link to="/distribution/data/weekly">
            <Button icon={<TableOutlined />}>주차별 데이터 보기</Button>
          </Link>
          <Link to="/distribution/data/products">
            <Button icon={<GoldOutlined />}>명품재고 보기</Button>
          </Link>
        </Space>
      </div>

      <Card size="small" style={{ marginBottom: 20 }}>
        <Dragger {...uploadProps} style={{ padding: "12px 8px" }}>
          <p className="ant-upload-drag-icon" style={{ margin: 0 }}>
            <InboxOutlined />
          </p>
          <p
            className="ant-upload-text"
            style={{ fontSize: 14, marginBottom: 4 }}
          >
            엑셀 파일을 끌어다 놓거나 클릭해서 선택
          </p>
          <p className="ant-upload-hint" style={{ fontSize: 12 }}>
            .xlsx, .xlsm 만 지원. 한 번에 한 파일씩 업로드합니다.
          </p>
        </Dragger>

        {pendingFile && (
          <div
            style={{
              marginTop: 12,
              padding: 12,
              background: "#fafafa",
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <Space>
              <Text strong>선택된 파일:</Text>
              <Text>{pendingFile.name}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {(pendingFile.size / 1024).toLocaleString("ko-KR", {
                  maximumFractionDigits: 1,
                })}{" "}
                KB
              </Text>
            </Space>
            <Space>
              <Button
                type="primary"
                icon={<CloudUploadOutlined />}
                loading={uploading}
                onClick={handleUpload}
              >
                업로드 시작
              </Button>
              <Button onClick={handleReset} disabled={uploading}>
                초기화
              </Button>
            </Space>
          </div>
        )}
      </Card>

      {uploading && (
        <Card size="small" style={{ marginBottom: 20 }}>
          <Spin tip="파일 파싱 및 적재 중…">
            <div style={{ minHeight: 60 }} />
          </Spin>
        </Card>
      )}

      {errorMsg && (
        <Alert
          type="error"
          showIcon
          message="업로드 실패"
          description={errorMsg}
          style={{ marginBottom: 20 }}
          closable
          onClose={() => setErrorMsg(null)}
        />
      )}

      {result && (
        <>
          <Alert
            type="success"
            showIcon
            message="업로드 완료"
            description="아래 결과를 확인하세요. 주차별 종합 데이터와 명품재고 페이지에서 적재된 항목을 조회할 수 있습니다."
            style={{ marginBottom: 12 }}
          />
          <Card size="small" style={{ marginBottom: 12 }}>
            <Descriptions
              column={{ xs: 1, sm: 2 }}
              size="small"
              bordered
              labelStyle={{ width: 180 }}
            >
              <Descriptions.Item label="파일명" span={2}>
                <Text strong>{result.file_name}</Text>
              </Descriptions.Item>
              <Descriptions.Item label="주차별 신규 적재">
                <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                  {result.summary_inserted.toLocaleString("ko-KR")}건
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="주차별 갱신">
                <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                  {result.summary_updated.toLocaleString("ko-KR")}건
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="명품재고 신규 적재">
                <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                  {result.products_inserted.toLocaleString("ko-KR")}건
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="명품재고 초기화">
                <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                  {result.products_wiped.toLocaleString("ko-KR")}건
                </Text>
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {result.warnings.length > 0 && (
            <Alert
              type="warning"
              showIcon
              message={`경고 ${result.warnings.length}건`}
              description={
                <ul style={{ margin: 0, paddingInlineStart: 18, fontSize: 13 }}>
                  {result.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              }
            />
          )}
        </>
      )}
    </div>
  );
}
