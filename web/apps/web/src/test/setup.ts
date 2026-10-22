// web/apps/web/src/test/setup.ts
// 시험마다 그린 것을 지우고, 로그인 상태를 비운다. 상태는 모듈 안의 값이라 시험 사이에 남는다.

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';
import { clearSession } from '../api/session';

afterEach(() => {
  cleanup();
  clearSession();
});
