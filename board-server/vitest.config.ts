import { defineConfig } from 'vitest/config';
import tsconfigPaths from 'vite-tsconfig-paths';

export default defineConfig({
  // Resolves the path aliases declared in tsconfig.json, including the ones
  // added by `nest g library`.
  plugins: [tsconfigPaths()],
  test: {
    globals: true,
    root: './',
    include: ['**/*.spec.ts'],
    // npm run test:cov 일 때만 잰다. 테스트가 불러오지 않은 파일도 0% 로 세도록 src 전체를 대상으로 둔다.
    // 마이그레이션은 만든 그대로의 SQL 이라 뺀다(앱 테스트가 DB 에 적용해 본다)
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.spec.ts', 'src/migrations/**'],
      // 로그에는 합계만, CI 의 작업 요약은 json-summary 를 읽어 적는다
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: './coverage/unit',
    },
  },
});
