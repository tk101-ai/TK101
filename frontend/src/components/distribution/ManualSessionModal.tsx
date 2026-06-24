import { useEffect, useMemo, useState } from "react";
import { Empty, Form, Input, Modal, Radio, Select, Spin, message } from "antd";
import { createManualSession, listPersonas } from "../../api/distribution";
import type { PersonaOut } from "../../api/distribution";
import type { DistributionLanguage } from "../../api/distribution_generate";
import { extractErrorDetail } from "../../utils/errorUtils";

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (sessionId: string) => void;
}

interface FormValues {
  sender_persona_id: string;
  receiver_persona_id: string;
  language: DistributionLanguage;
  group_chat_id?: string;
}

function activeLinkedAccounts(list: PersonaOut[]): PersonaOut[] {
  return list.filter((account) => account.active && account.is_logged_in);
}

function accountLabel(account: PersonaOut): string {
  const identity = account.business_name ?? account.display_name;
  const handle = account.telegram_username ? ` (@${account.telegram_username})` : "";
  return `${account.account_label} - ${identity}${handle}`;
}

export default function ManualSessionModal({ open, onClose, onCreated }: Props) {
  const [form] = Form.useForm<FormValues>();
  const selectedSenderId = Form.useWatch("sender_persona_id", form);
  const [accounts, setAccounts] = useState<PersonaOut[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (!open) return;
    const load = async () => {
      setLoading(true);
      try {
        setAccounts(activeLinkedAccounts(await listPersonas()));
        form.setFieldsValue({
          sender_persona_id: undefined,
          receiver_persona_id: undefined,
          language: "ko",
          group_chat_id: "",
        });
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "계정 목록 로드 실패"));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [open, form]);

  const senderOptions = useMemo(
    () =>
      accounts.map((account) => ({
        label: accountLabel(account),
        value: account.id,
      })),
    [accounts],
  );

  const receiverOptions = useMemo(
    () =>
      accounts
        .filter((account) => account.id !== selectedSenderId)
        .map((account) => ({
          label: accountLabel(account),
          value: account.id,
        })),
    [accounts, selectedSenderId],
  );

  const handleSubmit = async (values: FormValues) => {
    if (values.sender_persona_id === values.receiver_persona_id) {
      message.warning("첫 발송 계정과 대화 상대가 동일할 수 없습니다.");
      return;
    }
    setSubmitting(true);
    try {
      const { id } = await createManualSession({
        sender_persona_id: values.sender_persona_id,
        receiver_persona_id: values.receiver_persona_id,
        language: values.language,
        group_chat_id: (values.group_chat_id ?? "").trim() || null,
      });
      message.success("빈 세션을 만들었습니다. 메시지를 추가하세요.");
      form.resetFields();
      onCreated(id);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 생성 실패"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      title="수동 세션 만들기"
      open={open}
      onCancel={() => {
        if (!submitting) onClose();
      }}
      onOk={() => form.submit()}
      okText="만들기"
      cancelText="취소"
      okButtonProps={{
        loading: submitting,
        disabled: loading || accounts.length < 2,
      }}
      cancelButtonProps={{ disabled: submitting }}
      destroyOnClose
    >
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 24 }}>
          <Spin />
        </div>
      ) : accounts.length < 2 ? (
        <Empty
          description="수동 세션을 만들려면 연동되어 활성화된 계정이 2개 이상 필요합니다"
          imageStyle={{ height: 48 }}
        />
      ) : (
        <Form<FormValues> form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            name="sender_persona_id"
            label="첫 발송 계정"
            rules={[{ required: true, message: "첫 발송 계정을 선택하세요" }]}
          >
            <Select
              options={senderOptions}
              placeholder="계정 선택"
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
          <Form.Item
            name="receiver_persona_id"
            label="대화 상대"
            rules={[{ required: true, message: "대화 상대를 선택하세요" }]}
          >
            <Select
              options={receiverOptions}
              placeholder="계정 선택"
              showSearch
              optionFilterProp="label"
              disabled={!selectedSenderId}
            />
          </Form.Item>
          <Form.Item
            name="language"
            label="대화 언어"
            rules={[{ required: true, message: "언어를 선택하세요" }]}
          >
            <Radio.Group>
              <Radio.Button value="ko">한국어</Radio.Button>
              <Radio.Button value="zh">中文 (간체)</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="group_chat_id" label="그룹 chat id">
            <Input placeholder="-1001234567890 또는 @groupname" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
