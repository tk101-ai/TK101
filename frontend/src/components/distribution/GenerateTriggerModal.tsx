import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Divider,
  Empty,
  Form,
  Input,
  Modal,
  Radio,
  Select,
  Space,
  Spin,
  Switch,
  Tooltip,
  Typography,
  message,
} from "antd";
import { EditOutlined } from "@ant-design/icons";
import PersonaBusinessNameModal from "./PersonaBusinessNameModal";
import { listPersonas, listWeeklySummary } from "../../api/distribution";
import type {
  DistributionLanguage,
  PersonaOut,
  WeeklySummaryOut,
} from "../../api/distribution";
import {
  createUserScenario,
  discoverGroups,
  generateCustom,
  listScenarios,
} from "../../api/distribution_generate";
import type {
  GenerateCustomResult,
  GroupDialog,
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
  // 즉석 지시(저장 안 함). 채워지면 시나리오 미선택이어도 생성 가능.
  ad_hoc_instruction?: string;
  // "시나리오로 저장" 시 사용할 이름 + 첨부 권장 여부.
  save_name?: string;
  save_attachment?: boolean;
  // 그룹 송신 chat id (3명 방). 비우면 1:1 DM.
  group_chat_id?: string;
}

const LATEST_VALUE = "__latest__";
// 주차 데이터를 참고하지 않는 선택지 (매입/매출/재고 컨텍스트 미주입).
const NONE_VALUE = "__none__";

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
  const [adHoc, setAdHoc] = useState<string>("");
  const [savingScenario, setSavingScenario] = useState<boolean>(false);
  const [groupOptions, setGroupOptions] = useState<GroupDialog[]>([]);
  const [discovering, setDiscovering] = useState<boolean>(false);

  // 발신 페르소나 이름 인라인 수정 (모달 안에서 바로 변경 — 2026-06-08 요청).
  const [editingPersona, setEditingPersona] = useState<PersonaOut | null>(null);
  const [editOpen, setEditOpen] = useState<boolean>(false);

  // 한국 어드민 + 자격증명 보유만 노출하는 공통 필터.
  const onlyUsableKr = (list: PersonaOut[]): PersonaOut[] =>
    list.filter((p) => p.role === "domestic_admin" && p.has_credentials);

  // 이름 수정 후 목록만 다시 불러와 라벨을 즉시 갱신 (선택값은 유지).
  const reloadPersonas = async () => {
    try {
      setPersonas(onlyUsableKr(await listPersonas()));
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "페르소나 목록 갱신 실패"));
    }
  };

  // 선택한 발신 계정 기준으로 참여 중인 그룹을 조회해 chat_id 선택지로 노출.
  const handleDiscoverGroups = async () => {
    const personaId = (form.getFieldValue("sender_persona_ids") ?? [])[0];
    if (!personaId) {
      message.warning("먼저 발신 페르소나를 1명 이상 선택하세요 (그 계정으로 그룹 조회).");
      return;
    }
    setDiscovering(true);
    try {
      const groups = await discoverGroups(personaId);
      setGroupOptions(groups);
      if (groups.length === 0) {
        message.info("참여 중인 그룹이 없습니다. 먼저 텔레그램에서 그룹을 개설하세요.");
      }
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "그룹 조회 실패"));
    } finally {
      setDiscovering(false);
    }
  };

  const reloadScenarios = async () => {
    try {
      setScenarios(await listScenarios());
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "시나리오 목록 갱신 실패"));
    }
  };

  // 즉석 지시를 이름 붙여 재사용 가능한 시나리오로 저장 (저장형).
  const handleSaveScenario = async () => {
    const name = (form.getFieldValue("save_name") ?? "").trim();
    const instruction = (form.getFieldValue("ad_hoc_instruction") ?? "").trim();
    const language: DistributionLanguage = form.getFieldValue("language") ?? "zh";
    const attachment = Boolean(form.getFieldValue("save_attachment"));
    if (!instruction) {
      message.warning("저장하려면 먼저 '시나리오 지시' 내용을 입력하세요.");
      return;
    }
    if (!name) {
      message.warning("저장할 시나리오 이름을 입력하세요.");
      return;
    }
    setSavingScenario(true);
    try {
      const created = await createUserScenario({
        name,
        instruction,
        language,
        attachment_required: attachment,
      });
      message.success(`시나리오 저장됨: ${created.name}`);
      await reloadScenarios();
      form.setFieldsValue({ save_name: "" });
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "시나리오 저장 실패"));
    } finally {
      setSavingScenario(false);
    }
  };

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
        setPersonas(onlyUsableKr(personaList));
        setScenarios(scenarioList);
        setWeeks(weekList);

        // 기본값: 가장 최신 주차 + 전체 시나리오 미선택 + 전체 페르소나 미선택.
        form.setFieldsValue({
          sender_persona_ids: [],
          scenario_names: [],
          period_label: LATEST_VALUE,
          timing_profile: "normal",
          language: "ko",
          ad_hoc_instruction: "",
          save_name: "",
          save_attachment: false,
          group_chat_id: "",
        });
        setSenderIds([]);
        setScenarioNames([]);
        setAdHoc("");
        setGroupOptions([]);
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "초기 데이터 로드 실패"));
      } finally {
        setLoading(false);
      }
    };
    void loadAll();
  }, [open, form]);

  // 발신자 식별 라벨: 사업자명(수동) 우선, 없으면 연동 계정의 라이브 표시명.
  // 동기화된 @username 이 있으면 함께 노출해 실제 연동 계정을 확인 가능하게.
  // business_name 을 비우면(migration 030) 이 라벨이 라이브 display_name 으로 자동 표기됨.
  const personaLabel = (p: PersonaOut): string => {
    const identity = p.business_name ?? p.display_name;
    const handle = p.telegram_username ? ` (@${p.telegram_username})` : "";
    return `${p.account_label} — ${identity}${handle}`;
  };

  // 시나리오는 추가된 날짜순(백엔드 created_at 정렬)으로 내려오며, 1·2·3 번호를
  // 붙여 구분을 쉽게 한다. 영어 trigger_event 는 노출하지 않는다 (사용자 요청 2026-06-08).
  const scenarioOptions = useMemo(
    () =>
      scenarios.map((s, i) => ({
        label: `${i + 1}. ${s.name}`,
        value: s.name,
      })),
    [scenarios],
  );

  const weekOptions = useMemo(() => {
    const opts: { label: string; value: string }[] = [
      { label: "전체 — 최신 자동", value: LATEST_VALUE },
      { label: "참고 안 함 (주차 데이터 미사용)", value: NONE_VALUE },
    ];
    for (const w of weeks) {
      opts.push({
        label: `${w.period_label} (${w.period_start} ~ ${w.period_end})`,
        value: w.period_label,
      });
    }
    return opts;
  }, [weeks]);

  // 즉석 지시가 채워지면 시나리오 1개로 계산.
  const adHocCount = adHoc.trim() ? 1 : 0;
  const effectiveScenarioCount = scenarioNames.length + adHocCount;
  const expectedSessions = senderIds.length * effectiveScenarioCount;

  const handleClose = () => {
    if (submitting) {
      return;
    }
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: FormValues) => {
    const adHocText = (values.ad_hoc_instruction ?? "").trim();
    if (values.sender_persona_ids.length === 0) {
      message.warning("발신 페르소나를 1명 이상 선택하세요.");
      return;
    }
    if (values.scenario_names.length === 0 && !adHocText) {
      message.warning("시나리오를 선택하거나 '즉석 지시'를 입력하세요.");
      return;
    }
    setSubmitting(true);
    try {
      const useWeekly = values.period_label !== NONE_VALUE;
      const result = await generateCustom({
        sender_persona_ids: values.sender_persona_ids,
        scenario_names: values.scenario_names,
        period_label:
          values.period_label === LATEST_VALUE ||
          values.period_label === NONE_VALUE
            ? null
            : values.period_label,
        timing_profile: values.timing_profile ?? "normal",
        language: values.language ?? "ko",
        ad_hoc_instruction: adHocText || undefined,
        use_weekly_summary: useWeekly,
        group_chat_id: (values.group_chat_id ?? "").trim() || undefined,
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
    <>
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
            setAdHoc(all.ad_hoc_instruction ?? "");
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
            {personas.length === 0 ? (
              <Empty
                description="사용 가능한 한국 어드민 페르소나가 없습니다"
                imageStyle={{ height: 48 }}
              />
            ) : (
              <Checkbox.Group style={{ width: "100%" }}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 8,
                  }}
                >
                  {personas.map((p) => (
                    <div
                      key={p.id}
                      style={{ display: "flex", alignItems: "center", gap: 4 }}
                    >
                      <Checkbox value={p.id} style={{ flex: 1, marginRight: 0 }}>
                        {personaLabel(p)}
                      </Checkbox>
                      <Tooltip title="이름 수정">
                        <Button
                          type="text"
                          size="small"
                          icon={<EditOutlined />}
                          onClick={() => {
                            setEditingPersona(p);
                            setEditOpen(true);
                          }}
                        />
                      </Tooltip>
                    </div>
                  ))}
                </div>
              </Checkbox.Group>
            )}
          </Form.Item>

          <Form.Item
            name="scenario_names"
            label="시나리오 (활성 시나리오만 노출 · 즉석 지시 사용 시 미선택 가능)"
          >
            {scenarioOptions.length === 0 ? (
              <Empty
                description="저장된 시나리오가 없습니다 — 아래 '즉석 지시'로 바로 생성하거나 시나리오로 저장하세요"
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

          <Divider style={{ margin: "8px 0" }}>
            또는 — 즉석 지시 (AI 자유 생성)
          </Divider>

          <Form.Item
            name="ad_hoc_instruction"
            label="즉석 지시 (선택) — 자연어로 어떤 대화를 만들지 적으면 매번 새로 생성됩니다"
            help="예: 缺货抢货 — 매수측이 '공급 가능한 만큼 다 산다, 최대한 더 구해달라', 매도측은 '과다 주문 금지·재고 리스크 주의'. OFFER 엑셀은 검수 화면에서 첨부. (한국어로 써도 선택 언어로 생성)"
          >
            <Input.TextArea
              rows={4}
              placeholder="이번 대화에서 다룰 내용/흐름을 자유롭게 적으세요. 문장은 매번 AI가 새로 생성합니다."
            />
          </Form.Item>

          <Space.Compact style={{ width: "100%" }}>
            <Form.Item name="save_name" noStyle>
              <Input
                placeholder="이 지시를 시나리오로 저장할 이름 (재사용)"
                disabled={!adHoc.trim()}
              />
            </Form.Item>
            <Button
              onClick={handleSaveScenario}
              loading={savingScenario}
              disabled={!adHoc.trim()}
            >
              시나리오로 저장
            </Button>
          </Space.Compact>
          <Form.Item
            name="save_attachment"
            valuePropName="checked"
            style={{ marginTop: 8 }}
          >
            <Switch
              size="small"
              checkedChildren="첨부 권장"
              unCheckedChildren="첨부 권장"
            />
          </Form.Item>

          <Divider style={{ margin: "8px 0" }} />

          <Form.Item
            name="period_label"
            label="주차 데이터 (weekly_summary)"
            help="선택한 주차의 매입/매출/입금 요약이 LLM 컨텍스트로 주입됩니다. '참고 안 함'을 고르면 주차 데이터 없이 시나리오/지시만으로 생성합니다."
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

          <Divider style={{ margin: "8px 0" }}>그룹 송신 (3명 방, 선택)</Divider>

          <Form.Item
            name="group_chat_id"
            label="그룹 chat id (선택) — 입력 시 1:1 DM 대신 그룹에 게시"
            help="2 API 계정 + 관리자 1명이 있는 텔레그램 그룹의 chat id. 비우면 기존 1:1 송신. (송신은 페르소나 텔레그램 자격증명 등록 후 동작)"
          >
            <Input placeholder="-1001234567890 또는 @groupname" />
          </Form.Item>
          <Space.Compact style={{ width: "100%", marginBottom: 8 }}>
            <Button onClick={handleDiscoverGroups} loading={discovering}>
              내 그룹 찾기
            </Button>
            <Select
              style={{ flex: 1 }}
              placeholder="조회된 그룹에서 선택 (발신 계정 기준)"
              disabled={groupOptions.length === 0}
              options={groupOptions.map((g) => ({
                label: `${g.title} (${g.chat_id})`,
                value: g.chat_id,
              }))}
              onChange={(v) => form.setFieldsValue({ group_chat_id: v })}
            />
          </Space.Compact>

          <Divider style={{ margin: "8px 0" }} />

          <Alert
            type="info"
            showIcon
            message={
              <Text>
                예상 세션 수:{" "}
                <Text strong>
                  {senderIds.length} × {effectiveScenarioCount} ={" "}
                  {expectedSessions}
                </Text>
                {adHocCount > 0 ? " (즉석 지시 1개 포함)" : ""}
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

    {/* 발신 페르소나 이름 인라인 수정 — 저장 시 목록만 갱신해 라벨 즉시 반영. */}
    <PersonaBusinessNameModal
      open={editOpen}
      persona={editingPersona}
      onClose={() => {
        setEditOpen(false);
        setEditingPersona(null);
      }}
      onUpdated={reloadPersonas}
    />
    </>
  );
}
