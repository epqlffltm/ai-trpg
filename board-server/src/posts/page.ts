// board-server/src/posts/page.ts

/**
 * 목록을 쪽으로 나누는 셈. 순수한 함수들이다.
 *
 * 쪽 번호 방식이다. 글 목록 아래에 1 2 3 … 을 두는 게시판 화면에 맞춘다.
 * 몇 번째 쪽인지(page)와 한 쪽에 몇 개인지(size)를 받고, 전체가 몇 개인지(total)를 함께 돌려준다.
 */

/** 적지 않았을 때의 쪽 */
export const DEFAULT_PAGE = 1;
/** 적지 않았을 때 한 쪽에 담는 개수 */
export const DEFAULT_PAGE_SIZE = 20;
/** 한 쪽에 담을 수 있는 가장 큰 개수. 한 번에 전부 달라는 요청을 막는다 */
export const MAX_PAGE_SIZE = 50;
/** 볼 수 있는 가장 뒤의 쪽. 뒤로 갈수록 DB 가 건너뛰는 행이 많아져 느려진다 */
export const MAX_PAGE = 10000;

/** 목록의 한 쪽. */
export interface Page<Item> {
  items: Item[];
  /** 몇 번째 쪽인가. 1 부터 센다 */
  page: number;
  /** 한 쪽에 몇 개를 담는가 */
  size: number;
  /** 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
  total: number;
}

/** 이 쪽의 앞에서 건너뛸 개수. */
export function offsetOf(page: number, size: number): number {
  return (page - 1) * size;
}

/** 항목들을 쪽의 모양으로 묶는다. */
export function pageOf<Item>(
  items: Item[],
  page: number,
  size: number,
  total: number,
): Page<Item> {
  return { items, page, size, total };
}
