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
  },
});
