// web/e2e/playwright.config.ts
// 종단간 테스트(P2-4)의 설정. 실제 서버를 모두 띄운 스택(compose + docker-compose.e2e.yml)에 브라우저를 붙인다.
// CI 의 e2e 작업(.github/scripts/e2e.sh 의 test)이 부른다. 서버를 띄우는 일은 여기서 하지 않는다.
//
// 주소는 환경 변수로 받는다. 적지 않으면 로컬 compose 의 프록시(8080)와 Mailpit(8025)이다.
//   E2E_BASE_URL     화면과 API 를 함께 내주는 곳(프록시)
//   E2E_MAILPIT_URL  가입과 로그인의 메일 코드를 읽는 곳(Mailpit 의 API)
//
// 테스트는 한 줄로 돈다(workers 1). 같은 스택의 같은 계정과 테이블을 차례로 쓰고, 인증의 요청 수 제한(1분 10번)을 함께 쓴다.
// 실패하면 trace 와 스크린샷을 남긴다. CI 가 test-results 를 올린다.

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: '**/*.spec.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  // 한 흐름(가입부터 한 판까지)이 서술을 기다리므로 넉넉히 둔다
  timeout: 180_000,
  expect: { timeout: 20_000 },
  outputDir: 'test-results',
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:8080',
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
