import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Checkbox,
  Empty,
  Form,
  Modal,
  Radio,
  Select,
  Spin,
  Typography,
  message,
} from "antd";
import { listPersonas, listWeeklySummary } from "../../api/distribution";
import type {
  DistributionLanguage,
  PersonaOut,
  WeeklySummaryOut,
} from "../../api/distribution";
import {
  generateCustom,
  listScenarios,
} from "../../api/distribution_generate";
import type {
  GenerateCustomResult,
  ScenarioBrief,
  TimingProfile,
} from "../../api/distribution_generate";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Text, Paragraph } = Typography;

/**
 * 커스텀 생성 트리거 모달 (T9 Phase E-2).
 *
 * 사용자가 한국 어드민 페르소나 + 시나리오 + 주차를 선택하여 세션을 생성.
 * - 한국 어드민 페르소나는 자격증명 보유한 것만 노출.
 * - 시나리오는 active=True 만 노출.
 * - 주차는 "전체 — 최신 자동" + listWeeklySummary 결과.
 *
 * 백엔드: POST /api/distribution/generate-custom
 */

interface Props {
  open: boolean;
  onClose: () => void;
  onGenerated: (result: GenerateCustomResult) => void;
}

interface FormValues {
  sender_persona_ids: string[];
  scenario_names: string[];
  period_label: string | "__latest__";
  timing_profile: TimingProfile;
  language: DistributionLanguage;
}

const LATEST_VALUE = "__latest__";

export default function GenerateTriggerModal({
  open,
  onClose,
  onGenerated,
}: Props) {
  const [form] = Form.useForm<FormValues>();

  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const [personas, setPersonas] = useState<PersonaOut[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioBrief[]>([]);
  const [weeks, setWeeks] = useState<WeeklySummaryOut[]>([]);

  // 선택값 미리보기용 — useMemo 로 계산.
  const [senderIds, setSenderIds] = useState<string[]>([]);
  const [scenarioNames, setScenarioNames] = useState<string[]>([]);

  // 모달 오픈 시 한 번 데이터 로드.
  useEffect(() => {
    if (!open) {
      return;
    }
    const loadAll = async () => {
      setLoading(true);
      try {
        const [personaList, scenarioList, weekList] = await Promise.all([
          listPersonas(),
          listScenarios(),
          listWeeklySummary({ limit: 50 }),
        ]);
        // 한국 어드민 + 자격증명 보유만 노출.
        const usableKr = personaList.filter(
          (p) => p.role === "domestic_admin" && p.has_credentials,
        );
        setPersonas(usableKr);
        setScenarios(scenarioList);
        setWeeks(weekList);

        // 기본값: 가장 최신 주차 + 전체 시나리오 미선택 + 전체 페르소나 미선택.
        form.setFieldsValue({
          sender_persona_ids: [],
          scenario_names: [],
          period_label: LATEST_VALUE,
          timing_profile: "normal",
          language: "ko",
        });
        setSenderIds([]);
        setScenarioNames([]);
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "초기 데이터 로드 실패"));
      } finally {
        setLoading(false);
      }
    };
    void loadAll();
  }, [open, form]);

  const personaOptions = useMemo(
    () =>
      personas.map((p) => {
        // 발신자 식별: 사업자명(수동) 우선, 없으면 연동 계정의 라이브 표시명.
        // 동기화된 @username 이 있으면 함께 노출해 실제 연동 계정을 확인 가능하게.
        const identity = p.business_name ?? p.display_name;
        const handle = p.telegram_username ? ` (@${p.telegram_username})` : "";
        return {
          label: `${p.account_label} — ${identity}${handle}`,
          value: p.id,
        };
      }),
    [personas],
  );

  const scenarioOptions = useMemo(
    () =>
      scenarios.map((s) => ({
        label: `${s.name} (${s.trigger_event})`,
        value: s.name,
      })),
    [scenarios],
  );

  const weekOptions = useMemo(() => {
    const opts: { label: string; value: string }[] = [
      { label: "전체 — 최신 자동", value: LATEST_VALUE },
    ];
    for (const w of weeks) {
      opts.push({
        label: `${w.period_label} (${w.period_start} ~ ${w.period_end})`,
        value: w.period_label,
      });
    }
    return opts;
  }, [weeks]);

  const expectedSessions = senderIds.length * scenarioNames.length;

  const handleClose = () => {
    if (submitting) {
      return;
    }
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: FormValues) => {
    if (values.sender_persona_ids.length === 0) {
      message.warning("발신 페르소나를 1명 이상 선택하세요.");
      return;
    }
    if (values.scenario_names.length === 0) {
      message.warning("시나리오를 1개 이상 선택하세요.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await generateCustom({
        sender_persona_ids: values.sender_persona_ids,
        scenario_names: values.scenario_names,
        period_label:
          values.period_label === LATEST_VALUE ? null : values.period_label,
        timing_profile: values.timing_profile ?? "normal",
        language: values.language ?? "ko",
      });
      onGenerated(result);
      form.resetFields();
      onClose();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 생성에 실패했습니다"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="생성 트리거 — 페르소나 / 시나리오 / 주차 선택"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      okText={`생성 (예상 ${expectedSessions}건)`}
      cancelText="취소"
      okButtonProps={{
        loading: submitting,
        disabled: expectedSessions === 0 || loading,
      }}
      cancelButtonProps={{ disabled: submitting }}
      width={720}
      destroyOnClose
      maskClosable={!submitting}
    >
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 32 }}>
          <Spin />
        </div>
      ) : (
        <Form<FormValues>
          form={form}
          layout="vertical"
          onFinish={handleSubmit}
          onValuesChange={(_changed, all) => {
            setSenderIds(all.sender_persona_ids ?? []);
            setScenarioNames(all.scenario_names ?? []);
          }}
        >
          <Form.Item
            name="sender_persona_ids"
            label="발신 페르소나 (한국 어드민, 자격증명 보유만 노출)"
            rules={[
              {
                required: true,
                message: "발신 페르소나를 1명 이상 선택하세요",
                type: "array",
                min: 1,
              },
            ]}
          >
            {personaOptions.length === 0 ? (
              <Empty
                description="사용 가능한 한국 어드민 페르소나가 없습니다"
                imageStyle={{ height: 48 }}
              />
            ) : (
              <Checkbox.Group
                options={personaOptions}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                }}
              />
            )}
          </Form.Item>

          <Form.Item
            name="scenario_names"
            label="시나리오 (활성 시나리오만 노출)"
            rules={[
              {
                required: true,
                message: "시나리오를 1개 이상 선택하세요",
                type: "array",
                min: 1,
              },
            ]}
          >
            {scenarioOptions.length === 0 ? (
              <Empty
                description="활성 시나리오가 없습니다"
                imageStyle={{ height: 48 }}
              />
            ) : (
              <Checkbox.Group
                options={scenarioOptions}
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 8,
                }}
              />
            )}
          </Form.Item>

          <Form.Item
            name="period_label"
            label="주차 데이터 (weekly_summary)"
            help="선택한 주차의 매입/매출/입금 요약이 LLM 컨텍스트로 주입됩니다."
            rules={[{ required: true, message: "주차를 선택하세요" }]}
          >
            <Select options={weekOptions} placeholder="주차 선택" />
          </Form.Item>

          <Form.Item
            name="language"
            label="대화 언어"
            help="생성될 대화의 언어입니다. 中文 선택 시 두 페르소나가 자연스러운 간체 중국어로 대화합니다."
            rules={[{ required: true, message: "언어를 선택하세요" }]}
          >
            <Radio.Group>
              <Radio.Button value="ko">한국어</Radio.Button>
              <Radio.Button value="zh">中文 (간체)</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Form.Item
            name="timing_profile"
            label="메시지 간격 분포"
            help="AI 가 메시지 사이의 시간차(send_after_sec)를 어떻게 분배할지 결정합니다. 생성 후 검수 화면에서 메시지마다 수동 조정도 가능합니다."
            rules={[{ required: true, message: "간격 분포를 선택하세요" }]}
          >
            <Radio.Group>
              <Radio.Button value="short">짧음 (0~30분 · 빠른 핑퐁)</Radio.Button>
              <Radio.Button value="normal">보통 (5분~3시간 · 일상)</Radio.Button>
              <Radio.Button value="varied">다양함 (1분~12시간 · 하루 흐름)</Radio.Button>
            </Radio.Group>
          </Form.Item>

          <Alert
            type="info"
            showIcon
            message={
              <Text>
                예상 세션 수:{" "}
                <Text strong>
                  {senderIds.length} × {scenarioNames.length} ={" "}
                  {expectedSessions}
                </Text>
              </Text>
            }
            description={
              <Paragraph type="secondary" style={{ margin: 0 }}>
                각 (한국 페르소나, 시나리오) 조합마다 세션 1개가 status='pending'
                으로 생성됩니다. 베트남 어드민은 활성 1명이 자동 선택됩니다.
              </Paragraph>
            }
          />
        </Form>
      )}
    </Modal>
  );
}
