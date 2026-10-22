// web/eslint.config.js
// 화면의 린트 규칙. 앱과 공통 구성요소에 함께 쓴다.
// 타입스크립트의 권장 규칙과 React 훅의 규칙(훅의 차례, 의존성 목록)을 건다.
// 서버의 API 목록에서 만든 타입(src/api/generated)은 손으로 고치지 않으므로 보지 않는다.

import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['**/dist/**', '**/node_modules/**', '**/coverage/**', 'apps/web/src/api/generated/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // 쓰지 않는 값은 막는다. 이름이 _ 로 시작하면 일부러 버린 것이다
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    // 설정 파일과 도구(scripts/)는 Node 에서 돈다
    files: ['**/*.{js,mjs}'],
    languageOptions: { globals: globals.node },
  },
);
