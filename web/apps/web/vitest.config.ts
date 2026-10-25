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
  },
});
