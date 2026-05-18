import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Form,
  Input,
  Modal,
  Space,
  Typography,
  message,
} from "antd";
import { isAxiosError } from "axios";
import {
  initLogin,
  verifyCode,
  type PersonaOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Text, Paragraph } = Typography;

/**
 * 텔레그램 페르소나 SMS 로그인 모달 (T9 Phase A).
 *
 * 2단계 진행:
 *   1) "SMS 코드 발송" 버튼 → POST /personas/{id}/login-init → phone_code_hash 수신
 *   2) 사용자가 SMS 로 받은 코드 입력 → POST /personas/{id}/verify-code
 *      - 422 응답이면 2FA 비밀번호가 필요하다는 신호 → 비밀번호 필드 노출 후 재시도
 */

interface Props {
  open: boolean;
  persona: PersonaOut | null;
  onClose: () => void;
  onSuccess: () => void;
}

type LoginStep = "init" | "verify";

export default function PersonaLoginModal({
  open,
  persona,
  onClose,
  onSuccess,
}: Props) {
  const [step, setStep] = useState<LoginStep>("init");
  const [phoneCodeHash, setPhoneCodeHash] = useState<string>("");
  const [maskedPhone, setMaskedPhone] = useState<string>("");
  const [code, setCode] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [needs2FA, setNeeds2FA] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(false);

  const resetState = () => {
    setStep("init");
    setPhoneCodeHash("");
    setMaskedPhone("");
    setCode("");
    setPassword("");
    setNeeds2FA(false);
    setLoading(false);
  };

  // 모달이 닫힐 때마다 상태 초기화 — 다음 오픈 시 'init' 부터 시작.
  useEffect(() => {
    if (!open) {
      resetState();
    }
  }, [open]);

  const handleClose = () => {
    resetState();
    onClose();
  };

  const handleSendCode = async () => {
    if (!persona) return;
    setLoading(true);
    try {
      const res = await initLogin(persona.id);
      setPhoneCodeHash(res.phone_code_hash);
      setMaskedPhone(res.sent_to_phone_masked);
      setStep("verify");
      message.success("SMS 코드를 발송했습니다");
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "SMS 코드 발송에 실패했습니다"));
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async () => {
    if (!persona) return;
    if (!code.trim()) {
      message.warning("SMS 코드를 입력하세요");
      return;
    }
    setLoading(true);
    try {
      await verifyCode(persona.id, {
        phone_code_hash: phoneCodeHash,
        code: code.trim(),
        password: needs2FA ? password : null,
      });
      message.success("로그인에 성공했습니다");
      onSuccess();
      handleClose();
    } catch (err: unknown) {
      const status = isAxiosError(err) ? err.response?.status : undefined;
      if (status === 422) {
        // 2FA 비밀번호 필요 — 비밀번호 필드 노출 후 재시도 안내.
        setNeeds2FA(true);
        message.warning("2단계 인증 비밀번호를 입력 후 다시 시도하세요");
      } else {
        message.error(extractErrorDetail(err, "코드 검증에 실패했습니다"));
      }
    } finally {
      setLoading(false);
    }
  };

  const renderInitStep = () => (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="텔레그램 SMS 인증"
        description={
          <Paragraph style={{ margin: 0 }}>
            아래 버튼을 누르면 텔레그램에서 등록된 전화번호로 인증 코드를
            전송합니다. 받은 코드는 다음 단계에서 입력하세요.
          </Paragraph>
        }
      />
      {persona && (
        <Paragraph style={{ margin: 0 }}>
          <Text strong>{persona.account_label}</Text> ·{" "}
          <Text type="secondary">{persona.telegram_phone}</Text>
        </Paragraph>
      )}
      <Button
        type="primary"
        block
        loading={loading}
        onClick={handleSendCode}
      >
        SMS 코드 발송
      </Button>
    </Space>
  );

  const renderVerifyStep = () => (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Alert
        type="success"
        showIcon
        message="SMS 발송 완료"
        description={`코드 발송 대상: ${maskedPhone}`}
      />
      <Form layout="vertical" onFinish={handleVerify}>
        <Form.Item label="SMS 코드" required>
          <Input
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="텔레그램에서 받은 5~6자리 코드"
            maxLength={10}
            autoFocus
          />
        </Form.Item>

        {needs2FA && (
          <Form.Item
            label="2단계 인증 비밀번호"
            required
            help="텔레그램 2FA가 설정된 계정입니다. 비밀번호를 입력하세요."
          >
            <Input.Password
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="2FA 비밀번호"
            />
          </Form.Item>
        )}

        <Space style={{ width: "100%", justifyContent: "flex-end" }}>
          <Button onClick={handleClose} disabled={loading}>
            취소
          </Button>
          <Button type="primary" htmlType="submit" loading={loading}>
            확인
          </Button>
        </Space>
      </Form>
    </Space>
  );

  return (
    <Modal
      title="텔레그램 로그인"
      open={open}
      onCancel={handleClose}
      footer={null}
      destroyOnClose
      width={520}
    >
      {persona ? (
        step === "init" ? renderInitStep() : renderVerifyStep()
      ) : null}
    </Modal>
  );
}
