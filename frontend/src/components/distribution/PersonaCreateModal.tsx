import { Form, Input, InputNumber, Modal, Select, message } from "antd";
import { isAxiosError } from "axios";
import {
  PERSONA_ROLE_OPTIONS,
  createPersona,
  type PersonaCreatePayload,
  type PersonaOut,
  type PersonaRole,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

/**
 * 신규 텔레그램 계정 등록 모달 (T9 Phase A).
 *
 * - my.telegram.org 에서 발급받은 api_id/api_hash 가 필수.
 * - daily_msg_limit/warmup_days 는 송신 빈도 제한과 워밍업 기간을 정의.
 * - 백엔드가 409 (라벨 중복)/503 (Fernet 미설정) 를 반환할 수 있어
 *   사용자 친화 메시지로 안내한다.
 */

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (persona: PersonaOut) => void;
}

interface CreateFormValues {
  account_label: string;
  role: PersonaRole;
  display_name: string;
  telegram_phone: string;
  api_id: string;
  api_hash: string;
  daily_msg_limit: number;
  warmup_days: number;
}

export default function PersonaCreateModal({ open, onClose, onCreated }: Props) {
  const [form] = Form.useForm<CreateFormValues>();

  const handleClose = () => {
    form.resetFields();
    onClose();
  };

  const handleSubmit = async (values: CreateFormValues) => {
    const payload: PersonaCreatePayload = {
      account_label: values.account_label.trim(),
      role: values.role,
      display_name: values.display_name.trim(),
      telegram_phone: values.telegram_phone.trim(),
      api_id: values.api_id.trim(),
      api_hash: values.api_hash.trim(),
      daily_msg_limit: values.daily_msg_limit,
      warmup_days: values.warmup_days,
    };
    try {
      const persona = await createPersona(payload);
      message.success("텔레그램 계정이 등록되었습니다");
      form.resetFields();
      onCreated(persona);
      onClose();
    } catch (err: unknown) {
      // 백엔드가 자주 반환하는 상태코드에 친화 메시지 매핑.
      const status = isAxiosError(err) ? err.response?.status : undefined;
      if (status === 409) {
        message.error(extractErrorDetail(err, "이미 등록된 라벨입니다. 다른 라벨을 사용하세요."));
        return;
      }
      if (status === 503) {
        message.error(
          extractErrorDetail(
            err,
            "서버에 Fernet 키가 설정되지 않아 자격증명을 암호화할 수 없습니다. 관리자에게 문의하세요.",
          ),
        );
        return;
      }
      message.error(extractErrorDetail(err, "계정 등록에 실패했습니다"));
    }
  };

  return (
    <Modal
      title="새 텔레그램 계정 등록"
      open={open}
      onCancel={handleClose}
      onOk={() => form.submit()}
      okText="등록"
      cancelText="취소"
      destroyOnClose
      width={640}
    >
      <Form
        form={form}
        onFinish={handleSubmit}
        layout="vertical"
        initialValues={{
          role: "vietnam_admin",
          daily_msg_limit: 30,
          warmup_days: 7,
        }}
      >
        <div
          style={{
            display: "grid",
            gap: 12,
            gridTemplateColumns: "1fr 1fr",
          }}
        >
          <Form.Item
            name="account_label"
            label="계정 라벨"
            rules={[
              { required: true, message: "라벨을 입력하세요" },
              { max: 20, message: "최대 20자입니다" },
            ]}
          >
            <Input placeholder='예: "VN-A", "KR-A2"' maxLength={20} />
          </Form.Item>

          <Form.Item
            name="role"
            label="역할"
            rules={[{ required: true, message: "역할을 선택하세요" }]}
          >
            <Select options={PERSONA_ROLE_OPTIONS} placeholder="역할 선택" />
          </Form.Item>

          <Form.Item
            name="display_name"
            label="표시명"
            rules={[{ required: true, message: "표시명을 입력하세요" }]}
          >
            <Input placeholder="텔레그램에 표시될 이름" />
          </Form.Item>

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

          <Form.Item
            name="daily_msg_limit"
            label="일일 송신 한도"
            rules={[{ required: true, message: "한도를 입력하세요" }]}
          >
            <InputNumber min={1} max={1000} style={{ width: "100%" }} />
          </Form.Item>

          <Form.Item
            name="warmup_days"
            label="워밍업 기간 (일)"
            help="이 일수만큼 송신 빈도 낮게 유지"
            rules={[{ required: true, message: "워밍업 일수를 입력하세요" }]}
          >
            <InputNumber min={0} max={30} style={{ width: "100%" }} />
          </Form.Item>
        </div>
      </Form>
    </Modal>
  );
}
