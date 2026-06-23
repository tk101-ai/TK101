import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  Input,
  message,
  Row,
  Select,
  Space,
  Spin,
  Typography,
} from "antd";
import { useNavigate, useParams } from "react-router-dom";
import {
  createFormJob,
  getFormTemplate,
  patchFormTemplate,
  type FormTemplate,
  type FormVariable,
} from "../../api/forms";
import VariableEditor from "../../components/forms/VariableEditor";
import { DEPARTMENT_OPTIONS } from "../../config/modules";
import { extractErrorDetail } from "../../utils/errorUtils";
import FormWizardSteps from "../../components/forms/FormWizardSteps";

const { Text, Paragraph } = Typography;

/**
 * [2] 양식 매핑 검수 — FR-02.
 * 좌측: 양식 미리보기 (변수 위치 하이라이트, mock 단계는 placeholder)
 * 우측: 변수 테이블 (VariableEditor)
 */
export default function FormReviewPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [template, setTemplate] = useState<FormTemplate | null>(null);
  const [variables, setVariables] = useState<FormVariable[]>([]);
  const [name, setName] = useState("");
  const [departments, setDepartments] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let alive = true;
    (async () => {
      setLoading(true);
      try {
        const t = await getFormTemplate(id);
        if (!alive) return;
        setTemplate(t);
        setVariables(t.variables);
        setName(t.name);
        setDepartments(t.department_tags ?? []);
      } catch (e) {
        message.error(extractErrorDetail(e, "양식 정보를 불러오지 못했습니다"));
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  const handleSaveAndContinue = async () => {
    if (!template) return;
    setSaving(true);
    try {
      await patchFormTemplate(template.id, {
        name,
        department_tags: departments,
        variables,
      });
      message.success("양식 저장 완료 — 작성 잡 생성으로 이동");
      const job = await createFormJob(template.id);
      navigate(`/forms/jobs/${job.id}/sources`);
    } catch (e) {
      message.error(extractErrorDetail(e, "저장 실패"));
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 64 }}>
        <Spin />
      </div>
    );
  }
  if (!template) {
    return <Empty description="양식 정보가 없습니다" style={{ marginTop: 64 }} />;
  }

  const lowConfCount = variables.filter(
    (v) => v.confidence !== undefined && v.confidence !== null && v.confidence < 0.5,
  ).length;

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: "0 0 16px", fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
          변수 검수
        </h2>
        <FormWizardSteps current={1} />
        <Text type="secondary">
          자동 감지된 변수를 1회 확인·수정하고 양식 라이브러리에 저장합니다.
        </Text>
      </div>

      {variables.length >= 50 && (
        <Alert
          type="warning"
          showIcon
          message="변수 50개 이상 — 양식이 너무 복잡합니다"
          description="양식을 분할해 업로드하는 것을 권장합니다."
          style={{ marginBottom: 16 }}
        />
      )}
      {lowConfCount > 0 && (
        <Alert
          type="info"
          showIcon
          message={`신뢰도 0.5 미만 변수 ${lowConfCount}개 — 라벨/타입을 확인해 주세요`}
          style={{ marginBottom: 16 }}
        />
      )}

      <Row gutter={16}>
        <Col span={10}>
          <Card title="양식 미리보기" size="small" bodyStyle={{ minHeight: 540 }}>
            <Paragraph style={{ fontSize: 12, color: "#8c8c8c" }}>
              파일: {template.file_path} · 포맷 {template.file_format.toUpperCase()} · 해시{" "}
              {template.file_hash.slice(0, 12)}…
            </Paragraph>
            <div
              style={{
                background: "#fafafa",
                border: "1px solid #f0f0f0",
                borderRadius: 4,
                padding: 12,
                fontSize: 13,
                lineHeight: 1.8,
                color: "#595959",
                minHeight: 460,
              }}
            >
              <div>(양식 미리보기 — 변수 위치 하이라이트)</div>
              <div style={{ marginTop: 12 }}>
                {variables.map((v) => (
                  <div key={v.key} style={{ marginBottom: 6 }}>
                    <Text strong>{v.label}:</Text>{" "}
                    <Text code style={{ background: "#fff7e6" }}>{`{{${v.key}}}`}</Text>
                    {v.location && (
                      <Text type="secondary" style={{ fontSize: 11, marginLeft: 8 }}>
                        ({v.location})
                      </Text>
                    )}
                  </div>
                ))}
              </div>
              <Paragraph style={{ marginTop: 16, fontSize: 11, color: "#bfbfbf" }}>
                실제 양식 렌더링은 Phase 1에서 docx → HTML 미리보기로 고도화 예정.
              </Paragraph>
            </div>
          </Card>
        </Col>
        <Col span={14}>
          <Card title="변수 검수" size="small">
            <Space style={{ marginBottom: 12, width: "100%" }} direction="vertical">
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  양식명
                </Text>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="예: 월간 캠페인 보고서"
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  부서 태그 (다중 선택)
                </Text>
                <Select
                  mode="multiple"
                  value={departments}
                  onChange={setDepartments}
                  options={DEPARTMENT_OPTIONS}
                  style={{ width: "100%" }}
                  placeholder="부서를 선택하세요"
                />
              </div>
            </Space>
            <VariableEditor variables={variables} onChange={setVariables} />
            <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
              <Button onClick={() => navigate("/forms/new")}>이전 단계</Button>
              <Button type="primary" onClick={handleSaveAndContinue} loading={saving}>
                저장하고 자료 수집으로 이동
              </Button>
            </div>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
