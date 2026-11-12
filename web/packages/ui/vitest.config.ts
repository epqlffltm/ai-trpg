// web/packages/ui/vitest.config.ts
// 공통 구성요소의 시험. 브라우저 대신 jsdom 에서 그린다.

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    // 지나간 줄을 센다(npm run test:coverage, CI). 기준은 앱과 같은 생각이다(apps/web/vitest.config.ts)
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/**/*.test.{ts,tsx}', 'src/test-setup.ts', 'src/**/*.d.ts'],
      reporter: ['text-summary'],
      // 2026-11-12 에 잰 값: 문장 21.73, 갈래 26.98, 함수 37.5, 줄 23.8(%). 구성요소 대부분은 앱의 시험이 쓰며 지난다.
      // 여기의 시험은 둘(ChipGroup, ListSection)뿐이라 낮다. 정수로 내리고 1 을 뺐다
      thresholds: { statements: 20, branches: 25, functions: 36, lines: 22 },
    },
  },
});
