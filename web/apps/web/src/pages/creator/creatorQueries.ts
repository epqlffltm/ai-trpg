// web/apps/web/src/pages/creator/creatorQueries.ts
// 제작자 페이지(#992)의 열쇠와 부르는 함수. 서비스마다 열쇠가 따로라서 따로 불러오고 따로 실패한다.
// 공개 작품의 열쇠는 공개 목록의 것(['trpg','listings'], ['chat','characters'], ['story','public-worlds'])으로 시작한다.
// 그래서 보는 사람의 설정이 바뀌면 함께 다시 읽힌다(layout/ListingPreferencesSync.tsx). 로그인했는지도 열쇠에 넣는다.

import { queryOptions } from '@tanstack/react-query';
import { fetchCreator, fetchCreatorCharacters, fetchCreatorScenarios, fetchCreatorWorlds } from '../../api/creators';

export function creatorQuery(publicId: string) {
  return queryOptions({
    queryKey: ['auth', 'creators', publicId],
    queryFn: ({ signal }) => fetchCreator(publicId, signal),
  });
}

export function creatorScenariosQuery(publicId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['trpg', 'listings', 'creator', { publicId, signedIn }],
    queryFn: ({ signal }) => fetchCreatorScenarios(publicId, signal),
  });
}

export function creatorCharactersQuery(publicId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['chat', 'characters', 'creator', { publicId, signedIn }],
    queryFn: ({ signal }) => fetchCreatorCharacters(publicId, signal),
  });
}

export function creatorWorldsQuery(publicId: string, signedIn: boolean) {
  return queryOptions({
    queryKey: ['story', 'public-worlds', 'creator', { publicId, signedIn }],
    queryFn: ({ signal }) => fetchCreatorWorlds(publicId, signal),
  });
}
