/**
 * 브라우저 blob 다운로드 단일화 유틸.
 *
 * 앵커 생성 → href 지정 → 클릭 → revoke 시퀀스를 한 곳으로 모은다.
 * 기존에 페이지/컴포넌트마다 `removeChild` vs `a.remove()` 로 갈라져 있던
 * 중복(P2-1)을 통합한다. 동작은 동일하다.
 */
export function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}
