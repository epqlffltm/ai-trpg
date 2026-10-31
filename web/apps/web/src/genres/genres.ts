// web/apps/web/src/genres/genres.ts
// 장르의 차례와 화면의 이름. chat 의 캐릭터와 story 의 세계관이 같은 목록을 쓴다(asset-server/app/genres.py).
// TRPG 시나리오의 장르도 같은 값이다(trpg-server/app/listings/models.py). 서버는 값만 주고, 보이는 말은 여기서 정한다.
// 장르는 하나뿐이고 플레이 화면과 소개 화면의 테마를 정한다. 남성향·여성향과 성인용은 장르가 아니다(태그와 등급).

import type { AssetGenre } from '../api/types';

export type GenreValue = AssetGenre;

const GENRES: Record<GenreValue, string> = {
  fantasy: '판타지',
  wuxia: '무협',
  urban_fantasy: '현대 판타지',
  sf: 'SF',
  apocalypse: '아포칼립스',
  horror: '호러',
  mystery: '미스터리',
  romance: '로맨스',
  slice_of_life: '일상',
  alt_history: '대체역사',
  comedy: '코미디',
};

/** 고르는 칸의 차례 */
export const GENRE_VALUES = Object.keys(GENRES) as GenreValue[];

export function genreName(genre: GenreValue): string {
  return GENRES[genre];
}

/** 장르가 있으면 그 이름, 없으면 null. 표시들(칩)의 한 칸으로 쓴다 */
export function genreBadge(genre: GenreValue | null | undefined): string | null {
  return genre ? GENRES[genre] : null;
}

export function isGenreValue(value: string): value is GenreValue {
  return value in GENRES;
}
