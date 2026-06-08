import { useEffect } from "react";
import { Alert, Form, Input, Modal, Typography, message } from "antd";
import {
  updatePersona,
  type PersonaOut,
  type PersonaUpdatePayload,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Text } = Typography;

/**
 * 페르소나 사업자명/표시명 편집 모달 (T9 Phase C 보강).
 *
 * - 자격증명·세션은 손대지 않음. `PATCH /api/distribution/personas/{id}` 1회로 갱신.
 * - 두 필드 모두 선택. 빈 문자열은 null 로 정규화하여 백엔드에 전송.
 * - 자격증명 회전은 `PersonaCredentialsModal` 별도 흐름.
 */

interface Props {
  open: boolean;
  persona: PersonaOut | null;
  onClose: () => void;
  onUpdated: () => void;
}

interface FormValues {
  account_label: string;
  business_name: string;
  display_name: string;
}

function toNullable(value: string | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length === 0 ? null : trimmed;
}

export default function PersonaBusinessNameModal({
  open,
  persona,
  onClose,
  onUpdated,
}: Props) {
  const [form] = Form.useForm<FormValues>();

  // 모달이 열릴 때마다 현재 값으로 prefill.
  useEffect(() => {
    if (open && persona) {
      form.setFieldsValue({
        account_label: persona.account_label ?? "",
        business_name: persona.business_name ?? "",
        display_name: persona.display_name ?? "",
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
    const nextLabel = (values.account_label ?? "").trim();
    const nextBusinessName = toNullable(values.business_name);
    const nextDisplayName = (values.display_name ?? "").trim();

    const payload: PersonaUpdatePayload = {};
    if (nextLabel.length > 0 && nextLabel !== persona.account_label) {
      payload.account_label = nextLabel;
    }
    if (nextBusinessName !== (persona.business_name ?? null)) {
      payload.business_name = nextBusinessName;
    }
    if (nextDisplayName.length > 0 && nextDisplayName !== persona.display_name) {
      payload.display_name = nextDisplayName;
    }

    if (Object.keys(payload).length === 0) {
      message.info("변경 사항이 없습니다.");
      onClose();
      return;
    }

    try {
      await updatePersona(persona.id, payload);
      message.success("페르소나 정보를 갱신했습니다.");
      form.resetFields();
      onUpdated();
      onClose();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "페르소나 갱신에 실패했습니다"));
    }
  };

  return (
    <Modal
      title="라벨 / 사업자명 / 표시명 편집"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      okText="저장"
      cancelText="취소"
      destroyOnClose
      width={520}
    >
      {persona && (
        <>
          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 16 }}
            message={
              <span>
                <Text strong>{persona.account_label}</Text> 의 표시 정보를
                갱신합니다.
              </span>
            }
            description="자격증명·텔레그램 세션에는 영향이 없습니다."
          />
          <Form form={form} onFinish={handleSubmit} layout="vertical">
            <Form.Item
              name="account_label"
              label="라벨 (코드명)"
              help="영문/숫자/하이픈(-)/언더스코어(_)만, 최대 20자. 중복 불가. 예: LA, VN-admin"
              rules={[
                { max: 20, message: "최대 20자까지 입력 가능합니다" },
                {
                  pattern: /^[A-Za-z0-9_-]+$/,
                  message: "영문/숫자/하이픈/언더스코어만 사용할 수 있습니다",
                },
              ]}
            >
              <Input placeholder="예: LA / VN-admin" maxLength={20} />
            </Form.Item>

            <Form.Item
              name="business_name"
              label="사업자명"
              help="UI 표시용 라벨 (선택)"
              rules={[{ max: 200, message: "최대 200자까지 입력 가능합니다" }]}
            >
              <Input placeholder="예: 한일통상 / TK101 베트남" maxLength={200} />
            </Form.Item>

            <Form.Item
              name="display_name"
              label="표시명"
              help="페르소나 표시명 (선택, 빈 값이면 변경하지 않음)"
              rules={[{ max: 100, message: "최대 100자까지 입력 가능합니다" }]}
            >
              <Input placeholder="예: 김지원" maxLength={100} />
            </Form.Item>
          </Form>
        </>
      )}
    </Modal>
  );
}
