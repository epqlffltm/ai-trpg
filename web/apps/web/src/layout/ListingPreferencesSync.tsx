// web/apps/web/src/layout/ListingPreferencesSync.tsx
// 공개 목록에 실을 보는 사람의 설정(#986, #987)을 내 정보에서 읽어 맞춘다. 그리는 것은 없다.
// 값이 바뀌면(로그인, 로그아웃, 설정을 바꿈) 이미 읽은 공개 목록을 다시 읽게 한다. 목록의 열쇠에는 설정이 들어 있지 않다.

import { useQuery, useQueryClient, type Query } from '@tanstack/react-query';
import { useEffect } from 'react';
import { preferencesFor, setListingPreferences, type ListingPreferenceQuery } from '../api/listingPreferences';
import { meQuery } from '../auth/queries';
import { useSession } from '../auth/useSession';

/** 공개 목록의 열쇠(TRPG 의 시나리오, chat 의 캐릭터, story 의 세계관, 홍보 배너). 첫 화면, 탐색, 검색의 것이다 */
export function isPublicListing(query: Pick<Query, 'queryKey'>): boolean {
  const [service, kind] = query.queryKey;
  if (kind === 'banners') return service === 'trpg' || service === 'asset';
  return (service === 'trpg' && kind === 'listings') || (service === 'chat' && kind === 'characters') || (service === 'story' && kind === 'public-worlds');
}

export function ListingPreferencesSync() {
  const session = useSession();
  const me = useQuery({ ...meQuery(), enabled: session !== null });
  const queryClient = useQueryClient();
  const key = JSON.stringify(preferencesFor(session ? me.data : undefined));

  useEffect(() => {
    const next = JSON.parse(key) as ListingPreferenceQuery;
    if (setListingPreferences(next)) void queryClient.invalidateQueries({ predicate: isPublicListing });
  }, [key, queryClient]);

  return null;
}
