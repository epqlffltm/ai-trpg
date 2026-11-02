// web/apps/web/src/pages/search/searchView.ts
// 작품 검색(#984)의 검색어 규칙. 화면을 그리지 않는 순수한 함수다.
// 서버의 규칙(trpg-server/app/listings/search.py, asset-server/app/search.py)과 같다. 맞지 않는 검색어는 부르지 않고 까닭을 적는다.

/** 검색어의 길이. 서버의 상한과 같다 */
export const SEARCH_MAX_LENGTH = 50;

/** 앞뒤 공백을 지운 검색어 */
export function normalizeSearch(q: string): string {
  return q.trim();
}

/** "#"로 시작하면 태그 하나를 찾는다. "#" 뒤의 공백은 지운다. 태그가 아니면 null */
export function searchTag(q: string): string | null {
  const query = normalizeSearch(q);
  return query.startsWith('#') ? query.slice(1).trim() : null;
}

/** 검색어의 문제. 없으면 null. 빈 검색어는 문제가 아니라 아직 찾지 않은 것이다 */
export function searchProblem(q: string): string | null {
  const query = normalizeSearch(q);
  if (query === '') return null;
  const tag = searchTag(query);
  if (tag === '' || tag?.startsWith('#')) return '# 뒤에 태그를 적어 주세요.';
  return [...q].length > SEARCH_MAX_LENGTH ? `검색어는 ${SEARCH_MAX_LENGTH}자까지입니다.` : null;
}

/** 서버에 보내도 되는 검색어인가 */
export function isSearchable(q: string): boolean {
  return normalizeSearch(q) !== '' && searchProblem(q) === null;
}

/** 검색 결과 화면의 주소 */
export function searchPath(q: string): string {
  return `/search?${new URLSearchParams({ q: normalizeSearch(q) }).toString()}`;
}
