import { Button, Card, Form, Input, Select, Typography, Alert, message } from "antd";
import { LockOutlined, MailOutlined, UserOutlined, TeamOutlined } from "@ant-design/icons";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";
import { register } from "../api/auth";
import { DEPARTMENT_OPTIONS } from "../config/modules";

const { Title, Text } = Typography;

// 직원 셀프 가입. 부서는 본인이 선택(관리자 승인 시 확정), role 은 서버가 member 고정.
const DEPT_CHOICES = DEPARTMENT_OPTIONS.filter((o) => o.value !== "admin");

// 회사 도메인 외 가입 차단(서버 규칙과 동일). 대소문자 무시.
const COMPANY_EMAIL_DOMAIN = "@tk101global.com";

function isCompanyEmail(email: string): boolean {
  return email.trim().toLowerCase().endsWith(COMPANY_EMAIL_DOMAIN);
}

export default function Register() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [done, setDone] = useState(false);

  const handleSubmit = async (v: {
    name: string;
    email: string;
    password: string;
    department: string;
  }) => {
    try {
      await register(v);
      setDone(true);
      message.success("가입 신청 완료");
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        "가입에 실패했습니다";
      message.error(detail);
    }
  };

  return (
    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "#f0f2f5" }}>
      <Card style={{ width: 420, boxShadow: "0 2px 8px rgba(0,0,0,0.1)" }}>
        <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          TK101 직원 가입 신청
        </Title>
        {done ? (
          <>
            <Alert
              type="success"
              showIcon
              message="가입 신청이 접수되었습니다"
              description="관리자 승인 후 로그인할 수 있습니다. 승인까지 잠시 기다려주세요."
              style={{ marginBottom: 16 }}
            />
            <Button type="primary" block onClick={() => navigate("/login")}>
              로그인 화면으로
            </Button>
          </>
        ) : (
          <Form form={form} onFinish={handleSubmit} layout="vertical" size="large">
            <Form.Item name="name" rules={[{ required: true, message: "이름을 입력해주세요" }]}>
              <Input prefix={<UserOutlined />} placeholder="이름" />
            </Form.Item>
            <Form.Item
              name="email"
              rules={[
                { required: true, message: "이메일을 입력해주세요" },
                { type: "email", message: "이메일 형식이 올바르지 않습니다" },
                {
                  validator(_, value) {
                    if (!value || isCompanyEmail(value)) return Promise.resolve();
                    return Promise.reject(
                      new Error("회사 이메일(@tk101global.com)로만 가입할 수 있습니다"),
                    );
                  },
                },
              ]}
              extra="회사 이메일(@tk101global.com)로만 가입할 수 있습니다"
            >
              <Input prefix={<MailOutlined />} placeholder="회사 이메일" />
            </Form.Item>
            <Form.Item name="department" rules={[{ required: true, message: "부서를 선택해주세요" }]}>
              <Select
                placeholder="소속 부서"
                options={DEPT_CHOICES}
                suffixIcon={<TeamOutlined />}
              />
            </Form.Item>
            <Form.Item
              name="password"
              rules={[
                { required: true, message: "비밀번호를 입력해주세요" },
                { min: 8, message: "비밀번호는 8자 이상이어야 합니다" },
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="비밀번호 (8자 이상)" />
            </Form.Item>
            <Form.Item
              name="confirm"
              dependencies={["password"]}
              rules={[
                { required: true, message: "비밀번호를 다시 입력해주세요" },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue("password") === value) return Promise.resolve();
                    return Promise.reject(new Error("비밀번호가 일치하지 않습니다"));
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} placeholder="비밀번호 확인" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 8 }}>
              <Button type="primary" htmlType="submit" block>
                가입 신청
              </Button>
            </Form.Item>
            <Text type="secondary" style={{ display: "block", textAlign: "center" }}>
              이미 계정이 있으신가요? <Link to="/login">로그인</Link>
            </Text>
          </Form>
        )}
      </Card>
    </div>
  );
}
