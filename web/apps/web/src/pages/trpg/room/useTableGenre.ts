// web/apps/web/src/pages/trpg/room/useTableGenre.ts
// 테이블 방의 장르 테마(Stitch 23~33번)를 고를 장르. 테이블은 장르를 싣지 않으므로 그 시나리오의 소개(공개 목록)에서 읽는다.
// 읽지 못하면(공개를 내렸거나 서버가 멈췄다) 테마 없이 공통 디자인이다. 다시 묻지 않는다.

import { useQuery } from '@tanstack/react-query';
import { genreTheme } from '../../../genres/genreTheme';
import type { GenreValue } from '../../../genres/genres';
import { listingQuery } from '../queries';

export function useTableGenre(scenarioId: string): GenreValue | undefined {
  const listing = useQuery({ ...listingQuery(scenarioId, true), retry: false });
  return genreTheme(listing.data?.genre);
}
