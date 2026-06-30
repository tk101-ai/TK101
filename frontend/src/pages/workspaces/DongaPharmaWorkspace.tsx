import { useState } from "react";
import WorkspacePage from "./WorkspacePage";
import DongaReportModal from "./DongaReportModal";

/** 동아제약 작업공간(테스트) — 운영보고서 자동작성·보고서·시딩 가이드·댓글 분석. */
export default function DongaPharmaWorkspace() {
  const [reportOpen, setReportOpen] = useState(false);
  return (
    <>
      <WorkspacePage
        brand="동아제약"
        subtitle="운영보고서 자동 작성, 보고서·시딩 가이드 작성, 월간 보고서용 댓글 분석."
        tools={[
          {
            title: "운영보고서 자동 작성",
            desc: "구글시트(관리문서)의 해당 월 배포 데이터를 읽어 기존 운영보고서 양식의 표·요약을 자동으로 채웁니다. 홍보 방향·이슈는 AI 초안(검수 필요).",
            status: "ready",
            onClick: () => setReportOpen(true),
            actionLabel: "운영보고서 생성",
          },
          {
            title: "보고서 작성 (자유 형식)",
            desc: "주제·자료를 주면 AI가 보고서 초안을 작성합니다. 디자인 프리셋·HTML 덱도 사용 가능.",
            status: "ready",
            to: "/forms/generate?wizard=1",
            actionLabel: "문서 만들기",
          },
          {
            title: "시딩 가이드 작성",
            desc: "캠페인 시딩 가이드 문서를 AI로 초안 생성합니다.",
            status: "ready",
            to: "/forms/generate?wizard=1",
            actionLabel: "문서 만들기",
          },
          {
            title: "댓글 분석 (월간 보고서용)",
            desc: "SNS 채널 댓글을 수집·분석해 월간 보고서에 넣을 형식으로 정리하고, 텍스트(TXT)·CSV로 내보냅니다. 마케팅1팀 SNS 콘텐츠 형식 참고.",
            status: "soon",
            note: "댓글 수집 계정/데이터 전달 후 연동 예정 (CSV·TXT 내보내기 포함).",
          },
        ]}
      />
      <DongaReportModal open={reportOpen} onClose={() => setReportOpen(false)} />
    </>
  );
}
