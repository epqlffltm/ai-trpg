// web/apps/web/src/format/visibility.ts
// 작품의 공개 범위(asset 서버의 Visibility)를 글로 바꾸고, 링크 공개(#993)의 주소를 만든다. 순수한 함수다.
// 링크 공개는 목록과 검색에 나오지 않고 주소를 아는 사람만 연다. 주소는 작품의 소개 화면 주소다(작품 ID 가 그대로 링크다).

export type Visibility = 'private' | 'public' | 'unlisted';

const SHORT: Record<Visibility, string> = { private: '비공개', public: '공개', unlisted: '링크 공개' };

/** 목록의 한 단어 */
export function visibilityShort(visibility: Visibility): string {
  return SHORT[visibility];
}

/** 나눌 주소. origin 은 이 사이트의 주소(location.origin), path 는 소개 화면의 경로다 */
export function shareAddress(origin: string, path: string): string {
  return `${origin}${path}`;
}
