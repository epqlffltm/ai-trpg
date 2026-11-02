// web/apps/web/src/pages/search/searchQueries.ts
// 작품 검색(#984)의 열쇠와 부르는 함수. 서비스마다 열쇠가 따로라서 따로 불러오고 따로 실패한다.
// 공개 목록은 로그인했는지에 따라 내용이 다르다(로그인 전에는 전체이용가만). 그래서 열쇠에 그것을 넣는다.

import { queryOptions } from '@tanstack/react-query';
import { searchCharacters, searchScenarios, searchWorlds } from '../../api/search';

export function scenarioSearchQuery(q: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['trpg', 'listings', 'search', { q, signedIn }],
    queryFn: ({ signal }) => searchScenarios(q, signal),
  });
}

export function characterSearchQuery(q: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['chat', 'characters', 'search', { q, signedIn }],
    queryFn: ({ signal }) => searchCharacters(q, signal),
  });
}

export function worldSearchQuery(q: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['story', 'public-worlds', 'search', { q, signedIn }],
    queryFn: ({ signal }) => searchWorlds(q, signal),
  });
}
