import { useEffect } from "react";
import { Alert, Form, Input, Modal, Typography, message } from "antd";
import { isAxiosError } from "axios";
import {
  updatePersonaCredentials,
  type PersonaCredentialsPayload,
  type PersonaOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Text } = Typography;

/**
 * 자격증명 입력/갱신 모달 (T9 Phase A 보강).
 *
 * 용도:
 * - 시드된 placeholder 페르소나(+820000000000 등) 에 실 api_id/api_hash 주입
 * - 기존 페르소나의 자격증명 회전 (my.telegram.org 에서 hash 재발급한 경우)
 *
 * 동작:
 * - 백엔드가 Fernet 으로 즉시 재암호화 후 DB 갱신
 * - 기존 Telethon 세션은 자동 무효화 (불일치 가능성) → 재로그인 안내
 */

interface Props {
  open: boolean;
  persona: PersonaOut | null;
  onClose: () => void;
  onUpdated: () => void;
}

interface FormValues {
  telegram_phone: string;
  api_id: string;
  api_hash: string;
}

export default function PersonaCredentialsModal({
  open,
  persona,
  onClose,
  onUpdated,
}: Props) {
  const [form] = Form.useForm<FormValues>();

  // 모달이 열릴 때마다 기존 폰번호를 prefill (placeholder 도 그대로 노출).
  useEffect(() => {
    if (open && persona) {
      form.setFieldsValue({
        telegram_phone: persona.telegram_phone,
        api_id: "",
        api_hash: "",
      });
    } else if (!open) {
      form.resetFields();
    }
  }, [open, persona, form]);

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: FormValues) => {
    if (!persona) return;
    const payload: PersonaCredentialsPayload = {
      telegram_phone: values.telegram_phone.trim(),
      api_id: values.api_id.trim(),
      api_hash: values.api_hash.trim(),
    };
    try {
      await updatePersonaCredentials(persona.id, payload);
      message.success("자격증명을 갱신했습니다. 재로그인이 필요합니다.");
      form.resetFields();
      onUpdated();
      onClose();
    } catch (err: unknown) {
      const status = isAxiosError(err) ? err.response?.status : undefined;
      if (status === 503) {
        message.error(
          extractErrorDetail(
            err,
            "Fernet 키가 서버에 설정되지 않아 암호화할 수 없습니다.",
          ),
        );
        return;
      }
      message.error(extractErrorDetail(err, "자격증명 갱신에 실패했습니다"));
    }
  };

  return (
    <Modal
      title="자격증명 입력/갱신"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      okText="갱신"
      cancelText="취소"
      destroyOnClose
      width={560}
    >
      {persona && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={
              <span>
                <Text strong>{persona.account_label}</Text> 의 자격증명을
                갱신합니다.
              </span>
            }
            description="기존 Telethon 세션이 있으면 자동 무효화되며 재로그인이 필요합니다."
          />
          <Form form={form} onFinish={handleSubmit} layout="vertical">
            <Form.Item
              name="telegram_phone"
              label="전화번호"
              rules={[{ required: true, message: "전화번호를 입력하세요" }]}
            >
              <Input placeholder="+821012345678 (국가코드 포함)" />
            </Form.Item>

            <Form.Item
              name="api_id"
              label="API ID"
              rules={[{ required: true, message: "API ID를 입력하세요" }]}
            >
              <Input placeholder="my.telegram.org 발급 숫자 7~8자리" />
            </Form.Item>

            <Form.Item
              name="api_hash"
              label="API Hash"
              help="my.telegram.org 발급 32자 hex"
              rules={[
                { required: true, message: "API Hash를 입력하세요" },
                { len: 32, message: "API Hash 는 32자입니다" },
              ]}
            >
              <Input.Password placeholder="32자 hex 문자열" maxLength={32} />
            </Form.Item>
          </Form>
        </>
      )}
    </Modal>
  );
}
