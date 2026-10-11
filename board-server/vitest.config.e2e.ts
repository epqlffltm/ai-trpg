import { defineConfig } from 'vitest/config';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  plugins: [tsconfigPaths()],
  test: {
    globals: true,
    root: './',
    include: ['**/*.e2e-spec.ts'],
    // 테스트 파일마다 먼저 돈다. DB 주소를 읽고 테스트용 스키마로 고정한다
    setupFiles: ['./test/setup.ts'],
  },
});
