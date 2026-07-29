import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@playwright/test";

const configDir = path.dirname(fileURLToPath(import.meta.url));

/**
 * 핵심 사용자 플로우 E2E.
 *
 * 실제 API(uvicorn) + 실제 웹(next start) + 실제 PostgreSQL/Redis 위에서 돈다.
 * 컴포넌트 목킹 없이 배선 전체를 검증하는 것이 목적이다 — 특히 인증 경로는
 * 이후 httpOnly 쿠키 전환(B-1)이 갈아엎을 부분이라, 깨지면 여기서 드러나야 한다.
 *
 * 전용 DB(aim_e2e)를 쓴다. pytest(aim_test)와 분리해 두 스위트가 동시에 돌아도
 * 서로의 TRUNCATE에 맞지 않는다. 초기화(DROP/CREATE)와 스키마(alembic)는 모두
 * API 서버 기동 명령이 수행한다 — webServer가 globalSetup보다 먼저 시작되므로
 * 초기화를 globalSetup에 둘 수 없다(실측).
 */

const repoRoot = path.resolve(configDir, "../..");

export const E2E_DATABASE = "aim_e2e";
// API(psycopg)와 테스트 헬퍼(node-postgres)가 같은 DB를 다른 스킴으로 가리킨다.
export const E2E_DATABASE_URL_PG = `postgresql://aim:aim@localhost:5432/${E2E_DATABASE}`;
const E2E_DATABASE_URL_API = `postgresql+psycopg://aim:aim@localhost:5432/${E2E_DATABASE}`;

export default defineConfig({
  testDir: "./e2e",
  // 여정 테스트는 상태를 이어가므로 파일 내 순차 실행이 전제다.
  fullyParallel: false,
  workers: 1,
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure"
  },
  webServer: [
    {
      // 스키마를 create_all이 아니라 alembic으로 만든다 — 테스트가 도는 스키마가
      // 운영에 배포되는 스키마와 같은 절차로 생성되게(conftest.py와 같은 원칙).
      command:
        "uv run python scripts/reset_e2e_database.py && uv run alembic -c migrations/alembic.ini upgrade head && uv run uvicorn aim_api.main:app --port 8000",
      cwd: repoRoot,
      port: 8000,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        DATABASE_URL: E2E_DATABASE_URL_API,
        // 모든 테스트가 같은 IP에서 가입·로그인한다 — 스위트가 한도를 넘어
        // 서로를 망가뜨리지 않게 끈다(conftest.py와 같은 이유).
        RATE_LIMIT_ENABLED: "false"
      }
    },
    {
      // dev 서버는 방문 시점 lazy 컴파일이라 첫 페이지가 타임아웃 나기 쉽다.
      // 빌드 산출물은 NEXT_PUBLIC_API_URL 미지정 시 기본값(localhost:8000)을
      // 구워 넣으므로 그대로 API를 가리킨다.
      command: "corepack pnpm build && corepack pnpm start",
      cwd: configDir,
      port: 3000,
      reuseExistingServer: false,
      timeout: 180_000
    }
  ]
});
