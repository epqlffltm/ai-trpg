// web/apps/web/src/genres/genreTheme.ts
// 장르 테마(Stitch 23~33번)를 고르는 값. 플레이 화면과 소개 화면의 main 이 data-genre 로 단다(색은 genreThemes.css).
// 서버가 주는 장르가 아는 값이 아니거나 아직 모르면(불러오는 중) 테마 없이 공통 디자인이다. 순수한 함수다.

import { isGenreValue, type GenreValue } from './genres';

/** data-genre 에 달 값. 모르는 장르나 없으면 undefined(속성을 달지 않는다) */
export function genreTheme(genre: string | null | undefined): GenreValue | undefined {
  return genre && isGenreValue(genre) ? genre : undefined;
}
