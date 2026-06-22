/**
 * 다수의 비동기 작업을 동시성 상한(chunk) 으로 묶어 실행하는 유틸.
 *
 * 기존 일괄 처리 핸들러는 행 수만큼 `Promise.all` 을 무제한으로 띄워(예: 200건
 * 선택 시 200개 동시 PATCH) 서버/브라우저에 부하를 주고, 한 건이라도 실패하면
 * 전체가 reject 되어 부분 성공을 보고하지 못했다.
 *
 * `runBatched` 는 한 번에 최대 `concurrency` 개씩만 실행하고, 각 작업의 성공/실패를
 * 개별 집계해 `{ succeeded, failed }` 를 돌려준다(올-오어-낫싱 회피).
 */

export const DEFAULT_BULK_CONCURRENCY = 8;

export interface BatchResult {
  succeeded: number;
  failed: number;
}

export async function runBatched<T>(
  items: readonly T[],
  task: (item: T) => Promise<unknown>,
  concurrency: number = DEFAULT_BULK_CONCURRENCY,
): Promise<BatchResult> {
  const limit = Math.max(1, concurrency);
  let succeeded = 0;
  let failed = 0;

  for (let i = 0; i < items.length; i += limit) {
    const chunk = items.slice(i, i + limit);
    const results = await Promise.allSettled(chunk.map((item) => task(item)));
    for (const r of results) {
      if (r.status === "fulfilled") succeeded += 1;
      else failed += 1;
    }
  }

  return { succeeded, failed };
}
