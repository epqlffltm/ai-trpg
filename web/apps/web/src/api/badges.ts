// web/apps/web/src/api/badges.ts
// 내 활동 배지(#193, 인증 서버). 모든 배지와 받았는지. 배지는 서버가 출석, 본인인증, 초대 보상과 함께 준다. 화면은 읽기만 한다.

import { apiRequest } from './http';
import type { components } from './generated/auth';

export type MyBadges = components['schemas']['MyBadges'];
export type Badge = components['schemas']['Badge'];

/** 모든 배지를 차례대로, 받았으면 받은 시각과 함께. 로그인해야 부른다 */
export function fetchMyBadges(signal?: AbortSignal): Promise<MyBadges> {
  return apiRequest<MyBadges>('/api/v1/auth/me/badges', signal ? { signal } : {});
}
