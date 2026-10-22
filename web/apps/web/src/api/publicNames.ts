// web/apps/web/src/api/publicNames.ts
// 다른 사람의 공개 ID 로 닉네임을 한꺼번에 찾는다(인증 서버, #532). 로그인 없이 부른다.
// 다른 서버는 이름을 적어 두지 않고 공개 ID 만 준다. 화면이 한 쪽에 보이는 ID 를 모아 한 번에 묻는다.

import { apiRequest } from './http';
import type { PublicNames } from './types';

/** 한 번에 물을 수 있는 수(서버의 상한) */
export const PUBLIC_NAMES_LIMIT = 100;

/** 공개 ID → 닉네임. 탈퇴했거나 막은 계정이면 null */
export type NameBook = ReadonlyMap<string, string | null>;

export async function fetchPublicNames(ids: string[], signal?: AbortSignal): Promise<NameBook> {
  const response = await apiRequest<PublicNames>('/api/v1/auth/public-names', {
    query: { ids: ids.join(',') },
    skipRefresh: true,
    ...(signal ? { signal } : {}),
  });
  return new Map(response.names.map((entry) => [entry.public_id, entry.nickname]));
}
