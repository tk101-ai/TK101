import { useState } from "react";
import { Alert, Button, Card, message, Spin, Typography, Upload } from "antd";
import { InboxOutlined } from "@ant-design/icons";
import type { UploadFile } from "antd/es/upload/interface";
import { useNavigate } from "react-router-dom";
import { analyzeFormTemplate } from "../../api/forms";
import FormWizardSteps from "../../components/forms/FormWizardSteps";

const { Paragraph, Text } = Typography;

/**
 * [1] 양식 업로드 — FR-01.
 * .docx 양식을 업로드하면 백엔드가 변수를 자동 감지한다.
 * 분석 완료 후 [2] 매핑 검수 페이지로 이동.
 */
export default function FormUploadPage() {
  const navigate = useNavigate();
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [analyzing, setAnalyzing] = useState(false);

  const handleAnalyze = async () => {
    const file = fileList[0]?.originFileObj as File | undefined;
    if (!file) {
      message.error("양식 파일을 선택하세요");
      return;
    }
    setAnalyzing(true);
    try {
      const res = await analyzeFormTemplate(file);
      if (res.cache_hit) {
        message.success(
          `캐시 히트 — 기존 양식 v${res.version} 재사용 (분석 토큰 0)`,
        );
      } else {
        message.success(`변수 ${res.variables.length}개 자동 감지 완료`);
      }
      navigate(`/forms/templates/${res.template_id}/review`);
    } catch (err) {
      const msg =
        (err as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
        "양식 분석 실패";
      message.error(msg);
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <div style={{ maxWidth: 880 }}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
          양식 채우기
        </h2>
        <FormWizardSteps current={0} />
        <Text type="secondary">양식(.docx)을 올리면 빈 칸을 자동으로 감지합니다.</Text>
      </div>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 24 }}
        message="빈 양식을 올리면 AI가 변수를 자동으로 감지합니다"
        description={
          <Paragraph style={{ margin: 0 }}>
            <Text code>{`{{변수}}`}</Text>, <Text code>{`라벨: ___`}</Text>, 표 빈 셀, 체크박스
            등을 인식합니다. 동일 양식 재업로드 시 캐시가 적용되어 분석 비용이 0이 됩니다.
            지원 포맷: <Text strong>.docx</Text> (Phase 0), .xlsx (Phase 1), .hwpx (Phase 2).
          </Paragraph>
        }
      />

      <Spin spinning={analyzing} tip="AI가 양식을 분석하고 있습니다 (최대 8초)...">
        <Card>
          <Upload.Dragger
            accept=".docx,.xlsx,.hwpx"
            fileList={fileList}
            beforeUpload={() => false}
            maxCount={1}
            onChange={({ fileList: fl }) => setFileList(fl.slice(-1))}
            onRemove={() => setFileList([])}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">양식 파일을 끌어다 놓거나 클릭해 선택</p>
            <p className="ant-upload-hint" style={{ fontSize: 12 }}>
              빈 양식 1개 업로드 (50MB 이내) — 자료 파일이 아닌 양식 파일입니다
            </p>
          </Upload.Dragger>

          <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <Button onClick={() => navigate("/forms/library")}>양식 라이브러리</Button>
            <Button
              type="primary"
              onClick={handleAnalyze}
              disabled={fileList.length === 0}
              loading={analyzing}
            >
              양식 분석 시작
            </Button>
          </div>
        </Card>
      </Spin>
    </div>
  );
}
