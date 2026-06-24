import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Collapse,
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
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { EditOutlined } from "@ant-design/icons";
import PersonaBusinessNameModal from "./PersonaBusinessNameModal";
import { listPersonas } from "../../api/distribution";
import type { DistributionLanguage, PersonaOut } from "../../api/distribution";
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

interface Props {
  open: boolean;
  onClose: () => void;
  onGenerated: (result: GenerateCustomResult) => void;
}

interface FormValues {
  sender_persona_ids: string[];
  scenario_names: string[];
  timing_profile: TimingProfile;
  language: DistributionLanguage;
  ad_hoc_instruction?: string;
  save_name?: string;
  save_attachment?: boolean;
  group_chat_id?: string;
}

function activeLinkedAccounts(list: PersonaOut[]): PersonaOut[] {
  return list.filter((account) => account.active && account.is_logged_in);
}

export default function GenerateTriggerModal({ open, onClose, onGenerated }: Props) {
  const [form] = Form.useForm<FormValues>();

  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  const [accounts, setAccounts] = useState<PersonaOut[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioBrief[]>([]);

  const [senderIds, setSenderIds] = useState<string[]>([]);
  const [scenarioNames, setScenarioNames] = useState<string[]>([]);
  const [adHoc, setAdHoc] = useState<string>("");
  const [savingScenario, setSavingScenario] = useState<boolean>(false);
  const [groupOptions, setGroupOptions] = useState<GroupDialog[]>([]);
  const [discovering, setDiscovering] = useState<boolean>(false);

  const [editingAccount, setEditingAccount] = useState<PersonaOut | null>(null);
  const [editOpen, setEditOpen] = useState<boolean>(false);

  const reloadAccounts = async () => {
    try {
      setAccounts(activeLinkedAccounts(await listPersonas()));
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "계정 목록 갱신 실패"));
    }
  };

  const reloadScenarios = async () => {
    try {
      setScenarios(await listScenarios());
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "시나리오 목록 갱신 실패"));
    }
  };

  const handleDiscoverGroups = async () => {
    const accountId = (form.getFieldValue("sender_persona_ids") ?? [])[0];
    if (!accountId) {
      message.warning("먼저 첫 발송 계정을 1개 이상 선택하세요.");
      return;
    }
    setDiscovering(true);
    try {
      const groups = await discoverGroups(accountId);
      setGroupOptions(groups);
      if (groups.length === 0) {
        message.info("참여 중인 그룹이 없습니다.");
      }
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "그룹 조회 실패"));
    } finally {
      setDiscovering(false);
    }
  };

  const handleSaveScenario = async () => {
    const name = (form.getFieldValue("save_name") ?? "").trim();
    const instruction = (form.getFieldValue("ad_hoc_instruction") ?? "").trim();
    const language: DistributionLanguage = form.getFieldValue("language") ?? "ko";
    const attachment = Boolean(form.getFieldValue("save_attachment"));
    if (!instruction) {
      message.warning("저장할 시나리오 내용을 입력하세요.");
      return;
    }
    if (!name) {
      message.warning("시나리오 이름을 입력하세요.");
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
      const nextScenarioNames = Array.from(new Set([...scenarioNames, created.name]));
      message.success(`시나리오 저장됨: ${created.name}`);
      await reloadScenarios();
      form.setFieldsValue({
        scenario_names: nextScenarioNames,
        ad_hoc_instruction: "",
        save_name: "",
        save_attachment: false,
      });
      setScenarioNames(nextScenarioNames);
      setAdHoc("");
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "시나리오 저장 실패"));
    } finally {
      setSavingScenario(false);
    }
  };

  useEffect(() => {
    if (!open) {
      return;
    }
    const loadAll = async () => {
      setLoading(true);
      try {
        const [accountList, scenarioList] = await Promise.all([listPersonas(), listScenarios()]);
        setAccounts(activeLinkedAccounts(accountList));
        setScenarios(scenarioList);

        form.setFieldsValue({
          sender_persona_ids: [],
          scenario_names: [],
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

  const accountLabel = (account: PersonaOut): string => {
    const identity = account.business_name ?? account.display_name;
    const handle = account.telegram_username ? ` (@${account.telegram_username})` : "";
    return `${account.account_label} - ${identity}${handle}`;
  };

  const scenarioOptions = useMemo(
    () =>
      scenarios.map((scenario, index) => ({
        label: `${index + 1}. ${scenario.name}`,
        value: scenario.name,
      })),
    [scenarios],
  );

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
      message.warning("첫 발송 계정을 1개 이상 선택하세요.");
      return;
    }
    if (values.scenario_names.length === 0 && !adHocText) {
      message.warning("시나리오를 선택하거나 직접 작성하세요.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await generateCustom({
        sender_persona_ids: values.sender_persona_ids,
        scenario_names: values.scenario_names,
        timing_profile: values.timing_profile ?? "normal",
        language: values.language ?? "ko",
        ad_hoc_instruction: adHocText || undefined,
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
        title="대화 생성"
        open={open}
        onCancel={handleClose}
        onOk={() => form.submit()}
        okText={`생성 (${expectedSessions}건)`}
        cancelText="취소"
        okButtonProps={{
          loading: submitting,
          disabled: expectedSessions === 0 || loading,
        }}
        cancelButtonProps={{ disabled: submitting }}
        width={760}
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
            <Space direction="vertical" size={16} style={{ width: "100%" }}>
              <section>
                <Text strong>첫 발송 계정</Text>
                <Form.Item
                  name="sender_persona_ids"
                  style={{ marginTop: 8, marginBottom: 0 }}
                  rules={[
                    {
                      required: true,
                      message: "첫 발송 계정을 1개 이상 선택하세요",
                      type: "array",
                      min: 1,
                    },
                  ]}
                >
                  {accounts.length === 0 ? (
                    <Empty
                      description="연동되어 활성화된 텔레그램 계정이 없습니다"
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
                        {accounts.map((account) => (
                          <div
                            key={account.id}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: 4,
                            }}
                          >
                            <Checkbox value={account.id} style={{ flex: 1, marginRight: 0 }}>
                              {accountLabel(account)}
                              <Tag
                                color={account.role === "vietnam_admin" ? "blue" : "green"}
                                style={{ marginLeft: 6 }}
                              >
                                {account.role === "vietnam_admin" ? "베트남" : "국내"}
                              </Tag>
                            </Checkbox>
                            <Tooltip title="계정 표시 정보 수정">
                              <Button
                                type="text"
                                size="small"
                                icon={<EditOutlined />}
                                onClick={() => {
                                  setEditingAccount(account);
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
              </section>

              <section>
                <Text strong>저장된 시나리오</Text>
                <Form.Item name="scenario_names" style={{ marginTop: 8, marginBottom: 0 }}>
                  {scenarioOptions.length === 0 ? (
                    <Empty description="저장된 시나리오가 없습니다" imageStyle={{ height: 48 }} />
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
              </section>

              <section>
                <Text strong>직접 작성 시나리오</Text>
                <Form.Item name="ad_hoc_instruction" style={{ marginTop: 8, marginBottom: 8 }}>
                  <Input.TextArea
                    rows={4}
                    placeholder={[
                      "예: KR이 아래 링크 확인을 요청하고, VN이 확인하겠다고 답한 뒤 KR이 감사 인사로 마무리.",
                      "링크: https://docs.google.com/spreadsheets/d/...",
                    ].join("\n")}
                  />
                </Form.Item>

                <Space.Compact style={{ width: "100%" }}>
                  <Form.Item name="save_name" noStyle>
                    <Input placeholder="저장할 시나리오 이름" disabled={!adHoc.trim()} />
                  </Form.Item>
                  <Button
                    onClick={handleSaveScenario}
                    loading={savingScenario}
                    disabled={!adHoc.trim()}
                  >
                    저장
                  </Button>
                </Space.Compact>
                <Form.Item
                  name="save_attachment"
                  valuePropName="checked"
                  style={{ marginTop: 8, marginBottom: 0 }}
                >
                  <Switch size="small" checkedChildren="첨부 권장" unCheckedChildren="첨부 권장" />
                </Form.Item>
              </section>

              <Divider style={{ margin: 0 }} />

              <Form.Item
                name="language"
                label="대화 언어"
                style={{ marginBottom: 0 }}
                rules={[{ required: true, message: "언어를 선택하세요" }]}
              >
                <Radio.Group>
                  <Radio.Button value="ko">한국어</Radio.Button>
                  <Radio.Button value="zh">中文 (간체)</Radio.Button>
                </Radio.Group>
              </Form.Item>

              <Collapse
                size="small"
                items={[
                  {
                    key: "advanced",
                    label: "옵션",
                    children: (
                      <>
                        <Form.Item
                          name="timing_profile"
                          label="메시지 간격"
                          rules={[{ required: true, message: "간격 분포를 선택하세요" }]}
                        >
                          <Radio.Group>
                            <Radio.Button value="short">짧음</Radio.Button>
                            <Radio.Button value="normal">보통</Radio.Button>
                            <Radio.Button value="varied">다양함</Radio.Button>
                          </Radio.Group>
                        </Form.Item>

                        <Form.Item
                          name="group_chat_id"
                          label="그룹 chat id"
                          style={{ marginBottom: 8 }}
                        >
                          <Input placeholder="-1001234567890 또는 @groupname" />
                        </Form.Item>
                        <Space.Compact style={{ width: "100%" }}>
                          <Button onClick={handleDiscoverGroups} loading={discovering}>
                            그룹 찾기
                          </Button>
                          <Select
                            style={{ flex: 1 }}
                            placeholder="조회된 그룹 선택"
                            disabled={groupOptions.length === 0}
                            options={groupOptions.map((group) => ({
                              label: `${group.title} (${group.chat_id})`,
                              value: group.chat_id,
                            }))}
                            onChange={(value) => form.setFieldsValue({ group_chat_id: value })}
                          />
                        </Space.Compact>
                      </>
                    ),
                  },
                ]}
              />

              <Alert
                type="info"
                showIcon
                message={
                  <Text>
                    예상 세션 수:{" "}
                    <Text strong>
                      {senderIds.length} x {effectiveScenarioCount} = {expectedSessions}
                    </Text>
                    {adHocCount > 0 ? " (직접 작성 1개 포함)" : ""}
                  </Text>
                }
                description={
                  <Paragraph type="secondary" style={{ margin: 0 }}>
                    선택한 계정마다 세션 1개가 검수 대기 상태로 생성됩니다.
                  </Paragraph>
                }
              />
            </Space>
          </Form>
        )}
      </Modal>

      <PersonaBusinessNameModal
        open={editOpen}
        persona={editingAccount}
        onClose={() => {
          setEditOpen(false);
          setEditingAccount(null);
        }}
        onUpdated={reloadAccounts}
      />
    </>
  );
}
