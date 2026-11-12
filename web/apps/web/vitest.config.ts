// web/apps/web/vitest.config.ts
// 화면의 시험. 브라우저 대신 jsdom 에서 돈다. 서버는 부르지 않고 fetch 를 가짜로 바꾼다.

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
    unstubGlobals: true,
    // 시험 하나의 상한(기본 5초). 기다림 하나가 5초까지 걸릴 수 있어(src/test/setup.ts) 그 위에 다른 단계가 들어갈 자리를 둔다
    testTimeout: 15000,
    // 지나간 줄을 센다(npm run test:coverage, CI). 재는 것은 앱의 코드다. 시험, 시험의 도구, 서버의 API 목록에서 만든 타입은 뺀다.
    // 기준(thresholds)은 잰 값에서 조금 아래다. 내려가면 실패한다. 올라가면 기준도 올린다
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test/**', 'src/api/generated/**', 'src/**/*.d.ts'],
      reporter: ['text-summary'],
      // 2026-11-12 에 잰 값: 문장 89.88, 갈래 82.41, 함수 88.89, 줄 92.58(%). 정수로 내리고 1 을 뺐다
      thresholds: { statements: 88, branches: 81, functions: 87, lines: 91 },
    },
  },
});
