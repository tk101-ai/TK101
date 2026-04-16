/**
 * Sprint 0 skeleton — 기본 랜딩 페이지.
 * Sprint 1 dashboard-shell scope에서 /login, /dashboard 로 분리 예정.
 */
export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <div className="max-w-md text-center space-y-4">
        <h1 className="text-3xl font-bold text-primary">
          TK101 AI Platform
        </h1>
        <p className="text-muted-foreground">
          사내 40명 대상 AI 업무 자동화 플랫폼
        </p>
        <div className="text-sm text-muted-foreground space-y-1 mt-8">
          <p>✅ Sprint 0: 아키텍처 골조 완성</p>
          <p>🔨 Sprint 1: 인증 + 대시보드 (진행 예정)</p>
          <p>📅 Sprint 2: AI 채팅 + 백오피스</p>
        </div>
      </div>
    </main>
  );
}
