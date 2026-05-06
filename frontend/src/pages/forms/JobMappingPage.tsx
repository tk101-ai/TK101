import { useEffect, useMemo, useState } from "react";
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
import { CheckCircleOutlined, DownloadOutlined, FormOutlined } from "@ant-design/icons";
import { useNavigate, useParams } from "react-router-dom";
import {
  downloadJobOutput,
  getFormJob,
  patchJobMapping,
  regenerateJobMapping,
  renderJobDocx,
  type FormJobDetail,
} from "../../api/forms";
import MappingTable from "../../components/forms/MappingTable";

const { Text } = Typography;

/**
 * [4-5] 매핑 검수 + 누락 보강 — FR-04 / FR-05 / FR-06.
 * 좌측: 양식 미리보기 (변수 위치)
 * 우측: 매핑 테이블 + 출처 1클릭 펼쳐보기 + 누락 폼
 */
export default function JobMappingPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<FormJobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [regenKey, setRegenKey] = useState<string | null>(null);
  const [missingFormOpen, setMissingFormOpen] = useState(false);

  const refresh = async () => {
    try {
      const d = await getFormJob(id);
      setDetail(d);
    } catch {
      message.error("매핑 정보를 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
    } catch {
      message.error("매핑 수정 실패");
    }
  };

  const handleRegenerate = async (variableKey: string) => {
    setRegenKey(variableKey);
    try {
      await regenerateJobMapping(id, variableKey);
      message.success("Haiku 4.5 재생성 완료");
      await refresh();
    } catch {
      message.error("재생성 실패");
    } finally {
      setRegenKey(null);
    }
  };

  const handleConfirmAll = async () => {
    if (missingMappings.length > 0) {
      message.warning(`누락 변수 ${missingMappings.length}개를 먼저 입력하세요`);
      setMissingFormOpen(true);
      return;
    }
    setBusy(true);
    try {
      const res = await renderJobDocx(id);
      message.success("문서 생성 완료 — 다운로드를 시작합니다");
      const filename =
        `${detail?.template.name ?? "form"}_${new Date().toISOString().slice(0, 10)}.${
          detail?.template.file_format ?? "docx"
        }`;
      await downloadJobOutput(id, filename);
      // mock 환경 안내
      if (import.meta.env.VITE_FORMS_MOCK === "1") {
        message.info(`(mock) 다운로드 URL: ${res.download_url}`);
      }
    } catch {
      message.error("문서 생성 실패");
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
      <div style={{ marginBottom: 16, display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
            매핑 검수 · 누락 보강{" "}
            <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
              v0.1 · 4-5단계 / 5
            </Text>
          </h2>
          <Text type="secondary">
            양식 「{detail.template.name}」 · 자료 {detail.sources.length}개 ·{" "}
            매핑 {detail.mappings.length}개
          </Text>
        </div>
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
          <Card title="양식 미리보기" size="small" bodyStyle={{ minHeight: 600 }}>
            <div
              style={{
                background: "#fafafa",
                border: "1px solid #f0f0f0",
                borderRadius: 4,
                padding: 12,
                fontSize: 13,
                lineHeight: 1.8,
                color: "#595959",
                minHeight: 540,
              }}
            >
              {detail.template.variables.map((v) => {
                const m = detail.mappings.find((mp) => mp.variable_key === v.key);
                const filled = m?.value && m.value !== "";
                return (
                  <div key={v.key} style={{ marginBottom: 8 }}>
                    <Text strong>{v.label}: </Text>
                    {filled ? (
                      <Text>{m!.value}</Text>
                    ) : (
                      <Text type="danger" style={{ background: "#fff1f0", padding: "0 4px" }}>
                        (미채움)
                      </Text>
                    )}
                  </div>
                );
              })}
            </div>
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
    } catch {
      message.error("저장 실패");
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
