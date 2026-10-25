// web/apps/web/src/test/setup.ts
// 시험마다 그린 것을 지우고, 로그인 상태를 비운다. 상태는 모듈 안의 값이라 시험 사이에 남는다.
// findBy·waitFor 가 기다리는 상한을 5초로 둔다(기본 1초). 화면은 처음 갈 때 받는다(routing/pages.ts). 파일의 첫 시험이
// 큰 화면(시나리오 고치기 같은 것)의 모듈을 처음 읽는 동안 CI 처럼 붐비는 기계에서는 1초를 넘겨 그 시험만 떨어졌다.
// 기다림은 나타나는 대로 끝나므로 통과하는 시험은 느려지지 않는다.

import '@testing-library/jest-dom/vitest';
import { cleanup, configure } from '@testing-library/react';
import { afterEach } from 'vitest';
import { clearSession } from '../api/session';

configure({ asyncUtilTimeout: 5000 });

afterEach(() => {
  cleanup();
  clearSession();
});
