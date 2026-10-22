// web/packages/ui/vitest.config.ts
// 공통 구성요소의 시험. 브라우저 대신 jsdom 에서 그린다.

import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
});
