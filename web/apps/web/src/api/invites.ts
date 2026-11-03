// web/apps/web/src/api/invites.ts
// 내 초대 코드(#990, 인증 서버). 처음 부르면 서버가 만든다. 보상(실버)은 초대받은 사람이 본인인증을 마칠 때 서버가 정한다.

import { apiRequest } from './http';
import type { components } from './generated/auth';

export type MyInvite = components['schemas']['MyInvite'];

/** 내 초대 코드, 초대한 사람으로서 받은 보상의 수와 상한. 로그인해야 부른다 */
export function fetchMyInvite(signal?: AbortSignal): Promise<MyInvite> {
  return apiRequest<MyInvite>('/api/v1/auth/me/invite', signal ? { signal } : {});
}
