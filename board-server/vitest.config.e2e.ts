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
    // 테스트 파일을 하나씩 차례로 돌린다. 모두 같은 DB 의 같은 스키마(board_test)에 쓴다.
    // 함께 돌리면 한 파일이 비운 테이블에 다른 파일이 쓰고 있어서 결과가 흔들린다
    fileParallelism: false,
    // npm run test:e2e:cov 일 때만 잰다. 대상은 단위 테스트와 같다(vitest.config.ts)
    coverage: {
      provider: 'v8',
      include: ['src/**/*.ts'],
      exclude: ['src/**/*.spec.ts', 'src/migrations/**'],
      // 로그에는 합계만, CI 의 작업 요약은 json-summary 를 읽어 적는다
      reporter: ['text-summary', 'json-summary'],
      reportsDirectory: './coverage/e2e',
    },
  },
});
