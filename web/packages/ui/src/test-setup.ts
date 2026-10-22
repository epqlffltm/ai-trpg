// web/packages/ui/src/test-setup.ts
// 시험마다 그린 것을 지우고, toBeInTheDocument 같은 확인을 쓸 수 있게 한다.

import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});
