import path from "node:path";
import { fileURLToPath } from "node:url";
import type { Page } from "@playwright/test";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export const FIXTURES_DIR = path.resolve(__dirname, "../../fixtures");

/** 텍스트 픽스처 절대 경로로 변환. */
export const fixturePath = (name: string): string => path.join(FIXTURES_DIR, name);

/** 라이브 admin 계정으로 로그인. baseURL 기준. */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto("/login");
  // 라벨/플레이스홀더 다양성에 대비해 여러 후보 시도.
  const email = page
    .getByLabel(/이메일|email/i)
    .or(page.getByPlaceholder(/이메일|email/i))
    .first();
  const password = page
    .getByLabel(/비밀번호|password/i)
    .or(page.getByPlaceholder(/비밀번호|password/i))
    .first();
  await email.fill("admin@tk101.co.kr");
  await password.fill("admin123");
  await page.getByRole("button", { name: /로그인|login/i }).click();
  // 로그인 성공 시 /login 이탈.
  await page.waitForURL((url) => !url.pathname.startsWith("/login"), {
    timeout: 30_000,
  });
}
