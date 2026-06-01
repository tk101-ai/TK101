import { useEffect, useMemo, useState } from "react";
import { Form, Input, Modal, Radio, Select, Spin, message } from "antd";
import { createManualSession, listPersonas } from "../../api/distribution";
import type { PersonaOut } from "../../api/distribution";
import type { DistributionLanguage } from "../../api/distribution_generate";
import { extractErrorDetail } from "../../utils/errorUtils";

/**
 * 사용자가 직접 작성할 빈 세션 생성 모달.
 *
 * 발신/수신 페르소나 + 언어 + (선택) 그룹 chat id 를 받아 빈 세션을 만들고,
 * 생성된 세션 상세 화면으로 이동해 메시지를 직접 추가한다.
 * 백엔드: POST /api/distribution/sessions
 */

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

export default function ManualSessionModal({ open, onClose, onCreated }: Props) {
  const [form] = Form.useForm<FormValues>();
  const [personas, setPersonas] = useState<PersonaOut[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [submitting, setSubmitting] = useState<boolean>(false);

  useEffect(() => {
    if (!open) return;
    const load = async () => {
      setLoading(true);
      try {
        setPersonas(await listPersonas());
        form.setFieldsValue({
          sender_persona_id: undefined,
          receiver_persona_id: undefined,
          language: "zh",
          group_chat_id: "",
        });
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "페르소나 로드 실패"));
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [open, form]);

  const personaOptions = useMemo(
    () =>
      personas.map((p) => ({
        label: `${p.account_label} — ${p.business_name ?? p.display_name}`,
        value: p.id,
      })),
    [personas],
  );

  const handleSubmit = async (values: FormValues) => {
    if (values.sender_persona_id === values.receiver_persona_id) {
      message.warning("발신/수신 페르소나가 동일할 수 없습니다.");
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
      title="수동 세션 만들기 — 직접 작성"
      open={open}
      onCancel={() => {
        if (!submitting) onClose();
      }}
      onOk={() => form.submit()}
      okText="만들기"
      cancelText="취소"
      okButtonProps={{ loading: submitting, disabled: loading }}
      cancelButtonProps={{ disabled: submitting }}
      destroyOnClose
    >
      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: 24 }}>
          <Spin />
        </div>
      ) : (
        <Form<FormValues> form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            name="sender_persona_id"
            label="발신 페르소나"
            rules={[{ required: true, message: "발신 페르소나를 선택하세요" }]}
          >
            <Select options={personaOptions} placeholder="발신 계정 선택" showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item
            name="receiver_persona_id"
            label="수신 페르소나"
            rules={[{ required: true, message: "수신 페르소나를 선택하세요" }]}
          >
            <Select options={personaOptions} placeholder="수신 계정 선택" showSearch optionFilterProp="label" />
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
          <Form.Item
            name="group_chat_id"
            label="그룹 chat id (선택)"
            help="입력 시 1:1 대신 그룹(3명 방)에 게시. 비우면 1:1."
          >
            <Input placeholder="-1001234567890 또는 @groupname" />
          </Form.Item>
        </Form>
      )}
    </Modal>
  );
}
