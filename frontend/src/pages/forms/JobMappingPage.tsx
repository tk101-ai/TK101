import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  Empty,
  message,
  Modal,
  Row,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from "antd";
import {
  CheckCircleOutlined,
  DownloadOutlined,
  FormOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import {
  downloadJobOutput,
  getFormJob,
  patchJobMapping,
  regenerateJobMapping,
  renderJobDocx,
  previewJobDocx,
  type FormJobDetail,
} from "../../api/forms";
import MappingTable from "../../components/forms/MappingTable";
import FormWizardSteps from "../../components/forms/FormWizardSteps";
import { useAuth } from "../../hooks/useAuth";

const { Text } = Typography;

/**
 * 렌더 직전 검수 확정 (NFR-04 #4).
 * 백엔드 render 는 모든 required 변수의 매핑이 confirmed=true 여야 통과한다.
 * 누락 변수가 없는 상태에서 호출되므로, 값이 있는 매핑을 confirmed 로 PATCH 한다.
 * 이미 confirmed 인 매핑은 중복 호출하지 않는다.
 */
async function confirmMappingsBeforeRender(
  jobId: string,
  detail: FormJobDetail,
): Promise<void> {
  // 값이 있는 매핑만 확정한다. 필수인데 값이 없는 변수는 일부러 확정하지 않아
  // 백엔드 누락 검증(렌더 409 / missing_required)이 공란 문서 생성을 막도록 한다.
  const toConfirm = detail.mappings.filter(
    (m) => !m.confirmed && m.value !== null && m.value !== "",
  );
  for (const m of toConfirm) {
    await patchJobMapping(jobId, m.variable_key, { confirmed: true });
  }
}

/**
 * [4-5] 매핑 검수 + 누락 보강 — FR-04 / FR-05 / FR-06.
 * 좌측: 양식 미리보기 (변수 위치)
 * 우측: 매핑 테이블 + 출처 1클릭 펼쳐보기 + 누락 폼
 */
export default function JobMappingPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [detail, setDetail] = useState<FormJobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [regenKey, setRegenKey] = useState<string | null>(null);
  const [missingFormOpen, setMissingFormOpen] = useState(false);
  const [previewHtml, setPreviewHtml] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);

  // 현재 매핑 상태를 서버에서 즉석 렌더 → mammoth 로 HTML 변환해 실제 채워진 양식을
  // 미리 보여준다. 매핑 수정 후엔 "새로고침"으로 다시 렌더.
  const loadPreview = useCallback(async () => {
    setPreviewLoading(true);
    try {
      const buf = await previewJobDocx(id);
      // mammoth 는 무거워(~130kB) 미리보기 사용 시점에만 동적 로드(메인 번들 경량 유지).
      const mammoth = await import("mammoth");
      const convert =
        (mammoth as { convertToHtml?: typeof import("mammoth").convertToHtml })
          .convertToHtml ??
        (mammoth as { default?: typeof import("mammoth") }).default?.convertToHtml;
      const result = await convert!({ arrayBuffer: buf });
      setPreviewHtml(result.value || "<p style='color:#999'>(내용 없음)</p>");
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "미리보기 생성 실패");
    } finally {
      setPreviewLoading(false);
    }
  }, [id]);

  const refresh = async () => {
    try {
      const d = await getFormJob(id);
      setDetail(d);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "매핑 정보를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // id 변경 시 작업 매핑 재요청 (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // 잡 상세가 처음 로드되면 미리보기를 1회 자동 생성(이후엔 수동 새로고침).
  useEffect(() => {
    if (detail && !previewHtml && !previewLoading) void loadPreview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail]);

  const missingMappings = useMemo(() => {
    if (!detail) return [];
    return detail.template.variables.filter((v) => {
      const m = detail.mappings.find((mp) => mp.variable_key === v.key);
      return !m || m.value === null || m.value === "";
    });
  }, [detail]);

  const handleValueChange = async (variableKey: string, value: string) => {
    try {
      await patchJobMapping(id, variableKey, { value, manual_override: true });
      await refresh();
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "매핑 수정에 실패했습니다");
    }
  };

  const handleRegenerate = async (variableKey: string) => {
    setRegenKey(variableKey);
    try {
      await regenerateJobMapping(id, variableKey);
      message.success("재생성 완료");
      await refresh();
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "재생성에 실패했습니다");
    } finally {
      setRegenKey(null);
    }
  };

  const handleConfirmAll = async () => {
    if (!detail) return;
    if (missingMappings.length > 0) {
      message.warning(`누락 변수 ${missingMappings.length}개를 먼저 입력하세요`);
      setMissingFormOpen(true);
      return;
    }
    setBusy(true);
    try {
      // 검수 강제 (NFR-04 #4): 백엔드 render 는 모든 필수 변수가 confirmed 여야 통과.
      // "확정 후 다운로드" 가 사용자의 명시적 검수 확정 행위이므로, 값이 있는 매핑을
      // 모두 confirmed 처리한 뒤 render 한다.
      await confirmMappingsBeforeRender(id, detail);
      await renderJobDocx(id);
      message.success("문서 생성 완료 — 다운로드를 시작합니다");
      const filename =
        `${detail.template.name ?? "form"}_${new Date().toISOString().slice(0, 10)}.${
          detail.template.file_format ?? "docx"
        }`;
      await downloadJobOutput(id, filename);
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "문서 생성에 실패했습니다");
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: "center", padding: 64 }}>
        <Spin />
      </div>
    );
  }
  if (!detail) {
    return <Empty description="매핑 정보가 없습니다" style={{ marginTop: 64 }} />;
  }

  return (
    <div style={{ maxWidth: 1440 }}>
      <FormWizardSteps current={3} />
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            매핑 검수 · 누락 보강
          </h2>
          <Text type="secondary">
            양식 「{detail.template.name}」 · 자료 {detail.sources.length}개 ·{" "}
            매핑 {detail.mappings.length}개
          </Text>
        </div>
        {isAdmin && (
          <Space size="large">
            <Statistic
              title="누적 비용 (USD)"
              value={detail.cost_usd}
              precision={4}
              valueStyle={{ fontSize: 14 }}
            />
            <Statistic
              title="토큰 in/out"
              value={`${detail.total_tokens_in}/${detail.total_tokens_out}`}
              valueStyle={{ fontSize: 14 }}
            />
            {detail.langfuse_trace_id && (
              <Tag color="purple" style={{ marginTop: 8 }}>
                Langfuse {detail.langfuse_trace_id.slice(0, 8)}…
              </Tag>
            )}
          </Space>
        )}
      </div>

      {missingMappings.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`누락 변수 ${missingMappings.length}개 — 보강이 필요합니다`}
          description="자료에서 값을 찾지 못한 변수입니다. 아래 표에 직접 입력하거나 [누락 보강 폼]을 열어 일괄 입력하세요."
          action={
            <Button size="small" onClick={() => setMissingFormOpen(true)}>
              누락 보강 폼
            </Button>
          }
        />
      )}

      <Row gutter={16}>
        <Col span={9}>
          <Card
            title="양식 미리보기 (채워진 상태)"
            size="small"
            bodyStyle={{ minHeight: 600 }}
            extra={
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={previewLoading}
                onClick={loadPreview}
              >
                새로고침
              </Button>
            }
          >
            <Spin spinning={previewLoading}>
              <div
                className="docx-preview"
                style={{
                  background: "#fff",
                  border: "1px solid #f0f0f0",
                  borderRadius: 4,
                  padding: 16,
                  minHeight: 540,
                  maxHeight: 660,
                  overflow: "auto",
                  fontSize: 13,
                  lineHeight: 1.7,
                }}
                // mammoth 가 docx 텍스트를 이스케이프해 HTML 을 만든다(텍스트 노드 escape).
                // 사내 도구 + 자체 렌더 결과라 위험 낮음.
                dangerouslySetInnerHTML={{
                  __html:
                    previewHtml ||
                    "<p style='color:#999'>미리보기를 불러오는 중...</p>",
                }}
              />
            </Spin>
          </Card>
        </Col>
        <Col span={15}>
          <Card title="매핑 테이블" size="small">
            <MappingTable
              template={detail.template}
              mappings={detail.mappings}
              sources={detail.sources}
              onValueChange={handleValueChange}
              onRegenerate={handleRegenerate}
              regeneratingKey={regenKey}
            />
          </Card>
        </Col>
      </Row>

      <div style={{ marginTop: 16, display: "flex", justifyContent: "space-between" }}>
        <Button onClick={() => navigate(`/forms/jobs/${id}/sources`)}>
          이전 단계 (자료 수집)
        </Button>
        <Space>
          <Button icon={<FormOutlined />} onClick={() => setMissingFormOpen(true)}>
            누락 보강 폼 ({missingMappings.length})
          </Button>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            onClick={handleConfirmAll}
            loading={busy}
          >
            확정 후 다운로드
          </Button>
        </Space>
      </div>

      <MissingFormModal
        open={missingFormOpen}
        onClose={() => setMissingFormOpen(false)}
        detail={detail}
        onSave={async (kv) => {
          for (const [k, v] of Object.entries(kv)) {
            if (v === undefined) continue;
            await patchJobMapping(id, k, { value: v, manual_override: true });
          }
          message.success("누락 보강 완료");
          await refresh();
        }}
      />
    </div>
  );
}

interface MissingFormModalProps {
  open: boolean;
  onClose: () => void;
  detail: FormJobDetail;
  onSave: (kv: Record<string, string>) => Promise<void>;
}

function MissingFormModal({ open, onClose, detail, onSave }: MissingFormModalProps) {
  const missing = detail.template.variables.filter((v) => {
    const m = detail.mappings.find((mp) => mp.variable_key === v.key);
    return !m || m.value === null || m.value === "";
  });
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  const handleOk = async () => {
    setSaving(true);
    try {
      await onSave(values);
      setValues({});
      onClose();
    } catch (e) {
      message.error((e as any)?.response?.data?.detail || "저장에 실패했습니다");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      okText="저장"
      cancelText="취소"
      title={`누락 변수 ${missing.length}개 보강`}
      confirmLoading={saving}
      width={680}
      destroyOnClose
    >
      {missing.length === 0 ? (
        <Empty description="누락된 변수가 없습니다" />
      ) : (
        <Space direction="vertical" style={{ width: "100%" }}>
          {missing.map((v) => (
            <div key={v.key}>
              <Text strong>{v.label}</Text>{" "}
              <Text type="secondary" style={{ fontSize: 11 }}>
                {v.type}
                {v.required ? " · 필수" : ""}
              </Text>
              <input
                type={v.type === "date" ? "date" : v.type === "number" ? "number" : "text"}
                style={{
                  width: "100%",
                  padding: "6px 8px",
                  marginTop: 4,
                  border: "1px solid #d9d9d9",
                  borderRadius: 4,
                }}
                value={values[v.key] ?? ""}
                onChange={(e) =>
                  setValues((prev) => ({ ...prev, [v.key]: e.target.value }))
                }
              />
            </div>
          ))}
          <Text type="secondary" style={{ fontSize: 11 }}>
            <DownloadOutlined /> 입력값은 source kind=user_input 으로 출처 메타에 기록됩니다.
          </Text>
        </Space>
      )}
    </Modal>
  );
}
