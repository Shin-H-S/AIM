import { expect, test, type Page } from "@playwright/test";
import { Client } from "pg";
import { E2E_DATABASE_URL_PG } from "../playwright.config";

/**
 * 핵심 사용자 여정: 가입 → 프로젝트 생성 → 도메인 인증 → 검사 시작 → 결과 화면.
 *
 * 이 저장소는 Playwright를 제품 기능으로 이미 돌리면서 자기 UI에는 쓰지 않고
 * 있었다. 이 스위트의 일차 목적은 인증 경로의 회귀 방어다 — httpOnly 쿠키
 * 전환(B-1)이 갈아엎을 부분이 정확히 여기라서, 그 작업 전에 안전망이 필요하다.
 *
 * 테스트 더블은 단 하나, 도메인 소유권 인증이다. 실제 인증은 대상 사이트에
 * meta 태그를 심어야 통과하는데 E2E가 example.com을 수정할 수는 없다. DB에서
 * verified_at을 직접 마킹한다 — 이 단계의 실검증은 lab 실험대 도그푸딩이
 * 담당한다. 이메일 인증은 더블이 필요 없다: SMTP 미설정 환경은 가입 즉시
 * 인증 완료가 서비스의 실제 동작이다.
 *
 * 검사는 QUEUED 표시까지만 본다. 완주에는 워커·Lighthouse·대상 사이트가
 * 필요해 E2E가 취약해지고, 이 스위트가 지키려는 것은 스캔 파이프라인이 아니라
 * 인증·CRUD·큐잉의 배선이다.
 */

const runId = Date.now();
const email = `e2e-${runId}@example.com`;
const password = "correct horse battery staple";
const projectName = `E2E ${runId}`;

async function markProjectVerified(name: string): Promise<void> {
  const client = new Client({ connectionString: E2E_DATABASE_URL_PG });
  await client.connect();
  try {
    const result = await client.query(
      "UPDATE projects SET verified_at = now() WHERE name = $1",
      [name]
    );
    if (result.rowCount !== 1) {
      throw new Error(`expected to verify exactly one project, matched ${result.rowCount}`);
    }
  } finally {
    await client.end();
  }
}

async function logIn(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(password);
  await page.getByRole("button", { name: "로그인" }).click();
  await page.waitForURL("**/dashboard");
}

test.describe.serial("핵심 플로우", () => {
  test("가입하면 자동 로그인되어 프로젝트 생성으로 이어진다", async ({ page }) => {
    await page.goto("/signup");
    await page.locator("#signup-email").fill(email);
    await page.locator("#signup-password").fill(password);
    await page.locator("#signup-confirm-password").fill(password);
    await page.getByRole("button", { name: /가입/ }).click();

    // SMTP 미설정 → 즉시 인증 → 자동 로그인 → 새 프로젝트 화면.
    await page.waitForURL("**/projects/new");
  });

  test("프로젝트를 만들면 도메인 인증 안내로 이어진다", async ({ page }) => {
    await logIn(page);
    await page.goto("/projects/new");
    await page.locator("#name").fill(projectName);
    await page.locator("#service_url").fill("https://example.com");
    await page.getByRole("button", { name: /생성|등록|저장/ }).click();

    // 신규 생성은 대시보드가 아니라 설정 화면으로 간다 — 도메인 인증(meta 태그)
    // 안내가 거기 있기 때문이다. 인증 전이라는 사실이 화면에 드러나야 한다.
    await page.waitForURL(/\/projects\/[0-9a-f-]+\/settings/);
    await expect(page.getByText(/인증/).first()).toBeVisible();

    // 대시보드에서도 이 프로젝트는 검사를 시작할 수 없는 상태로 보여야 한다.
    await page.goto("/dashboard");
    const card = page.locator("article, section, li").filter({ hasText: projectName }).first();
    await expect(card.getByRole("button", { name: "검증 필요" })).toBeVisible();
  });

  test("인증된 프로젝트는 검사를 시작해 대기 상태 화면에 도착한다", async ({ page }) => {
    await markProjectVerified(projectName);

    await logIn(page);
    const card = page.locator("article, section, li").filter({ hasText: projectName }).first();
    await card.getByRole("button", { name: "검사 시작" }).click();

    // 성공 시 검사 상세로 이동한다. 워커가 없으므로 QUEUED에 머문다 —
    // 여기까지가 이 스위트의 책임 범위다.
    await page.waitForURL(/\/projects\/[0-9a-f-]+\/check-runs\/[0-9a-f-]+/);
    await expect(page.getByText("대기 중").first()).toBeVisible();
    // 판정 헤더(R1)는 진행 중에도 첫 블록에서 상태를 말해야 한다.
    await expect(page.getByText("검사가 아직 진행 중입니다.")).toBeVisible();
  });

  test("로그아웃하면 대시보드가 로그인으로 안내한다", async ({ page }) => {
    await logIn(page);
    // 로그아웃은 계정 드롭다운(aria-label="계정 메뉴") 안의 menuitem이다.
    await page.getByRole("button", { name: "계정 메뉴" }).click();
    await page.getByRole("menuitem", { name: "로그아웃" }).click();
    // 로그아웃은 서버가 쿠키를 지운 뒤(응답 완료 후) 홈으로 이동한다.
    // 그 이동을 기다리지 않고 goto 하면 앱의 이동이 테스트의 이동을 중단시킨다.
    await page.waitForURL((url) => url.pathname === "/");

    await page.goto("/dashboard");
    await expect(page.getByRole("link", { name: "로그인 페이지로 이동" })).toBeVisible();
  });
});

test("잘못된 비밀번호는 대시보드에 들어가지 못한다", async ({ page }) => {
  await page.goto("/login");
  await page.locator("#email").fill(email);
  await page.locator("#password").fill("definitely-wrong-password");
  await page.getByRole("button", { name: "로그인" }).click();

  // 어떤 문구를 쓰든, 핵심 계약은 "대시보드로 넘어가지 않는다"이다.
  await page.waitForTimeout(1_500);
  expect(page.url()).not.toContain("/dashboard");
});
