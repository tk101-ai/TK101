import { expect, test } from "@playwright/test";
import { fixturePath, loginAsAdmin } from "./helpers";

/**
 * S1 — 양식 자동 작성 전체 플로우
 *
 * 단계: 로그인 → 양식 라이브러리 → 첫 양식으로 작성 잡 생성 →
 *       자료 다중 업로드(텍스트 3개) → 매핑 실행 → 검수 페이지에서 결과 캡쳐
 *
 * 주의: 라이브 환경에 새 작성 잡과 자료가 생성된다.
 *       매핑 단계는 Claude API 호출이 발생하므로 비용 소량 발생 (~$0.01).
 */
test.describe("S1 — 양식 자동 작성 전체 플로우", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("기존 양식 → 자료 3개 업로드 → 매핑 → 검수 진입", async ({ page }) => {
    // 1. 양식 라이브러리 진입.
    await page.goto("/forms");
    await expect(page).toHaveURL(/\/forms/);

    // 2. 첫 양식 카드 클릭하여 작성 잡 만들기.
    //    Ant Design Card title 또는 행에 양식명이 표시되어 있을 것.
    const firstFormLink = page
      .getByRole("link")
      .or(page.getByRole("button", { name: /작성|이 양식으로/ }))
      .first();
    await firstFormLink.waitFor({ state: "visible", timeout: 15_000 });
    await firstFormLink.click();

    // 변수 검수 단계 또는 작성 잡 생성 흐름 진입까지 대기.
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/s1-step02-form-detail.png", fullPage: true });

    // 2-1. 양식 분석 후 변수 검수 페이지에서 "저장하고 자료 수집으로 이동" 버튼 가능.
    const proceedBtn = page.getByRole("button", { name: /자료 수집|저장하고/ });
    if (await proceedBtn.isVisible().catch(() => false)) {
      await proceedBtn.click();
      await page.waitForLoadState("networkidle");
    }

    // 3. 자료 수집 페이지인지 확인.
    await expect(page.getByText(/자료 수집|수집된 자료/)).toBeVisible({ timeout: 15_000 });

    // 4. "자료 추가" 모달 오픈.
    await page.getByRole("button", { name: /자료 추가/ }).click();

    // 5. 사용자 업로드 탭으로 전환.
    await page.getByText(/사용자 업로드/).click();

    // 6. 텍스트 픽스처 3개 동시 업로드 (개선요청 #1 검증).
    const fileInput = page.locator('input[type="file"]').first();
    await fileInput.setInputFiles([
      fixturePath("sample_company_intro.txt"),
      fixturePath("sample_marketing_report.txt"),
      fixturePath("sample_business_info.txt"),
    ]);

    // 7. 모달 확인 버튼.
    await page.getByRole("button", { name: /^추가$|확인/ }).click();

    // 8. 부분 실패 없이 3개 모두 성공해야 함.
    await expect(page.getByText(/3개 자료 업로드 완료/)).toBeVisible({ timeout: 60_000 });

    // 9. 수집된 자료 카운트 확인.
    await expect(page.getByText(/수집된 자료 \(3개\)/)).toBeVisible();

    await page.screenshot({ path: "test-results/s1-step09-sources.png", fullPage: true });

    // 10. 매핑 실행 — Claude API 호출. 최대 90초 대기.
    await page.getByRole("button", { name: /매핑 실행|매핑/ }).click();

    // 11. 검수 페이지로 이동 확인.
    await page.waitForURL(/\/review/, { timeout: 90_000 });

    // 12. 검수 페이지 결과 스크린샷 — 매핑 부족 진단(개선요청 #2)에 활용.
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: "test-results/s1-step12-review.png", fullPage: true });

    // 13. 변수 테이블이 표시되어 있어야 함.
    await expect(page.getByText(/변수|매핑/)).toBeVisible();
  });
});
