// web/apps/web/src/api/blocks.ts
// 막은 제작자와 태그(#988). 인증 서버가 가진다. 막은 것은 /me 의 blocks 에 실리고, 공개 목록을 부를 때 싣는다(listingPreferences.ts).
//   - PUT, DELETE /me/blocks/creators/{공개 ID}: 제작자를 막고 푼다. 자기 자신이면 400(block_self)
//   - PUT, DELETE /me/blocks/tags/{태그}: 태그를 막고 푼다. 태그는 주소에 인코딩한다. 1~20자가 아니면 400(invalid_tag)
//   - 답은 바뀐 뒤의 막은 것 전체다. 제작자 100명, 태그 30개를 넘으면 409(block_limit). 다시 해도 같다

import type { components } from './generated/auth';
import { apiRequest } from './http';

export type Blocks = components['schemas']['Blocks'];

/** 막을 수 있는 수. 인증 서버의 accounts/blocks.py 와 같다 */
export const MAX_BLOCKED_CREATORS = 100;
export const MAX_BLOCKED_TAGS = 30;
export const BLOCKED_TAG_MAX_LENGTH = 20;

const BASE = '/api/v1/auth/me/blocks';

/** blocked 가 참이면 막고, 거짓이면 푼다 */
export function setCreatorBlock(publicId: string, blocked: boolean): Promise<Blocks> {
  return apiRequest<Blocks>(`${BASE}/creators/${encodeURIComponent(publicId)}`, { method: blocked ? 'PUT' : 'DELETE' });
}

/** blocked 가 참이면 막고, 거짓이면 푼다 */
export function setTagBlock(tag: string, blocked: boolean): Promise<Blocks> {
  return apiRequest<Blocks>(`${BASE}/tags/${encodeURIComponent(tag)}`, { method: blocked ? 'PUT' : 'DELETE' });
}
