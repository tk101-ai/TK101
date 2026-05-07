import { expect, test } from "@playwright/test";
import path from "node:path";
import fs from "node:fs/promises";
import os from "node:os";
import { fixturePath, loginAsAdmin } from "./helpers";

/**
 * S2 — 다중 업로드 부분 실패 처리
 *
 * 정상 텍스트 2개 + 한도 초과 가짜 큰 파일 1개를 동시에 업로드해서
 * "2개 성공 · 1개 실패" 경고가 뜨고 카운트는 2가 되는지 검증.
 *
 * 한도 초과 파일은 임시 디렉토리에 51MB 더미를 생성해 사용한다 (서버 한도 50MB).
 */
test.describe("S2 — 다중 업로드 부분 실패 처리", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("2개 성공 + 1개 한도 초과 → 부분 성공 안내 + 카운트 2", async ({ page }) => {
    // 임시 51MB 더미 파일 생성.
    const tmpDir = await fs.mkdtemp(path.join(os.tmpdir(), "tk101-e2e-"));
    const oversizePath = path.join(tmpDir, "oversize_dummy.pdf");
    await fs.writeFile(oversizePath, Buffer.alloc(51 * 1024 * 1024));

    try {
      await page.goto("/forms");
      const firstFormLink = page.getByRole("link").first();
      await firstFormLink.waitFor({ state: "visible", timeout: 15_000 });
      await firstFormLink.click();
      await page.waitForLoadState("networkidle");

      const proceedBtn = page.getByRole("button", { name: /자료 수집|저장하고/ });
      if (await proceedBtn.isVisible().catch(() => false)) {
        await proceedBtn.click();
        await page.waitForLoadState("networkidle");
      }

      await page.getByRole("button", { name: /자료 추가/ }).click();
      await page.getByText(/사용자 업로드/).click();

      const fileInput = page.locator('input[type="file"]').first();
      await fileInput.setInputFiles([
        fixturePath("sample_company_intro.txt"),
        fixturePath("sample_marketing_report.txt"),
        oversizePath,
      ]);

      await page.getByRole("button", { name: /^추가$|확인/ }).click();

      // "2개 성공 · 1개 실패" 또는 부분 실패 경고 메시지.
      await expect(page.getByText(/성공.*실패|2개 성공/)).toBeVisible({ timeout: 60_000 });

      // 카운트는 2여야 함.
      await expect(page.getByText(/수집된 자료 \(2개\)/)).toBeVisible();

      await page.screenshot({ path: "test-results/s2-partial.png", fullPage: true });
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });
});
