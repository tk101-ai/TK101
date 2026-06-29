import WorkspacePage from "./WorkspacePage";

/** 현대백화점 작업공간(테스트, 뉴미디어팀) — 체험단 번역·초안 검수·팔로워 정리. */
export default function HyundaiWorkspace() {
  return (
    <WorkspacePage
      brand="현대백화점"
      subtitle="뉴미디어팀 — 체험단 본문/자막 한국어 번역, 초안 검수, 팔로워·인터랙션 정리. (샘플 데이터·API·계정은 추후 연동)"
      tools={[
        {
          title: "체험단 본문 한국어 번역 → Word",
          desc: "체험단 본문·자막을 한국어로 번역하고 Word로 정리합니다. 현재는 체험단 번역 도구로 번역 가능.",
          status: "ready",
          to: "/marketing/review-translation",
          actionLabel: "체험단 번역 열기",
          note: "번역 결과 Word 일괄 내보내기는 추가 예정.",
        },
        {
          title: "초안 검수 (미국 체험단)",
          desc: "비원어민 미국 체험단 초안을 AI로 1차 검수 — 의미 왜곡, 원어민 수준 표현 점검(현재 수작업 인당 ~30분).",
          status: "soon",
          note: "검수 프롬프트·샘플 데이터 확정 후 연동 예정.",
        },
        {
          title: "팔로워·인터랙션 정리 (일별/월별 + 그래프)",
          desc: "계정별 팔로워·인터랙션을 일별/월별로 자동 집계하고 그래프로 표시합니다. (현재는 백단/치엔과 수기 엑셀 기입)",
          status: "soon",
          note: "데이터 API·계정 전달 후 자동 집계·그래프 연동 예정.",
        },
      ]}
    />
  );
}
