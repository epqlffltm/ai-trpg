// web/apps/web/src/pages/guardian/guardianPresets.ts
// 보호자의 시험용 본인확인 창(A4)의 처음 값과 빠른 고르기. 회원의 것(A3)과 식별값이 달라야 회원 본인으로 막히지 않는다.

import type { AgePreset } from '../identity/FakeIdentityForm';

export const GUARDIAN_FAKE_DI = 'dev-guardian';

export const GUARDIAN_PRESETS: readonly AgePreset[] = [
  { age: 45, label: '성인 보호자(만 45세)' },
  { age: 18, label: '성년 전(만 18세, 막힘)' },
];
