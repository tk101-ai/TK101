import { Steps } from "antd";

/**
 * 양식 채우기 4단계 공유 진행바. 각 페이지가 자신의 단계 index 를 넘긴다.
 * 페이지 간 이동은 기존 라우팅 그대로지만, 사용자가 "지금 몇 단계인지"를
 * 글자(N단계/5)가 아니라 시각적 Steps 로 항상 보게 한다.
 */
const FORM_WIZARD_STEPS = [
  { title: "양식 업로드" },
  { title: "변수 검수" },
  { title: "자료 수집" },
  { title: "매핑·완성" },
];

interface FormWizardStepsProps {
  current: number;
}

export default function FormWizardSteps({ current }: FormWizardStepsProps) {
  return (
    <Steps
      current={current}
      size="small"
      items={FORM_WIZARD_STEPS}
      style={{ maxWidth: 720, marginBottom: 20 }}
    />
  );
}
