// web/apps/web/src/api/listingPreferences.ts
// 공개 목록을 부를 때 싣는 보는 사람의 설정(#986, #987). 성인 작품 숨김과 성향이다.
// 설정은 인증 서버의 내 정보(/me 의 content_settings)에 있다. 목록을 내는 서버(게임, asset)는 인증 서버를 부르지 않으므로
// 화면이 읽어 목록의 주소에 싣는다(?hide_adult=true&orientation=male). 소개 하나를 여는 주소에는 싣지 않는다.
// 지금 값은 이 모듈이 쥐고, 내 정보를 읽거나 설정을 바꾸면 layout/ListingPreferencesSync.tsx 가 고친다.

import type { Me } from './types';

/** 목록의 주소에 더할 값. 거르지 않는 것은 싣지 않는다 */
export type ListingPreferenceQuery = { hide_adult?: string; orientation?: string };

let current: ListingPreferenceQuery = {};

/** 지금 목록에 실을 값 */
export function listingPreferences(): ListingPreferenceQuery {
  return current;
}

/** 지금 값을 바꾼다. 바뀌었으면 true(목록을 다시 읽어야 한다) */
export function setListingPreferences(next: ListingPreferenceQuery): boolean {
  const changed = JSON.stringify(next) !== JSON.stringify(current);
  current = next;
  return changed;
}

/**
 * 내 정보에서 목록에 실을 값. 로그인하지 않았으면 비어 있다.
 * 성인 작품은 볼 수 있는 사람(성인 확인)이 표시를 껐을 때만 숨기라고 싣는다. 볼 수 없는 사람에게는 서버가 이미 뺀다.
 */
export function preferencesFor(me: Me | undefined): ListingPreferenceQuery {
  if (!me) return {};
  // 인증 서버가 아직 이 칸을 주지 않으면(먼저 올라간 화면) 거르지 않는다
  const settings = me.content_settings ?? {};
  const query: ListingPreferenceQuery = {};
  if (me.identity?.adult_content && settings.show_adult_content === false) query.hide_adult = 'true';
  if (settings.orientation && settings.orientation !== 'all') query.orientation = settings.orientation;
  return query;
}
