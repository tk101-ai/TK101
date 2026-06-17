import { Button, Card, Form, Input, message, Typography } from "antd";
import { LockOutlined, MailOutlined } from "@ant-design/icons";
import { login } from "../api/auth";
import { Link, useNavigate } from "react-router-dom";

const { Text } = Typography;

const { Title } = Typography;

export default function Login({ onLogin }: { onLogin: () => void }) {
  const navigate = useNavigate();
  const [form] = Form.useForm();

  const handleSubmit = async (values: { email: string; password: string }) => {
    try {
      const res = await login(values);
      localStorage.setItem("token", res.data.access_token);
      onLogin();
      navigate("/");
    } catch {
      message.error("로그인 실패: 이메일 또는 비밀번호를 확인해주세요");
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 400, boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
        <Title level={3} style={{ textAlign: "center", marginBottom: 32 }}>
          TK101 AI Platform
        </Title>
        <Form form={form} onFinish={handleSubmit} layout="vertical" size="large">
          <Form.Item name="email" rules={[{ required: true, message: "이메일을 입력해주세요" }]}>
            <Input prefix={<MailOutlined />} placeholder="이메일" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: "비밀번호를 입력해주세요" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="비밀번호" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 8 }}>
            <Button type="primary" htmlType="submit" block>
              로그인
            </Button>
          </Form.Item>
          <Text type="secondary" style={{ display: "block", textAlign: "center" }}>
            계정이 없으신가요? <Link to="/register">직원 가입 신청</Link>
          </Text>
        </Form>
      </Card>
    </div>
  );
}
