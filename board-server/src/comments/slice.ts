// board-server/src/comments/slice.ts

/**
 * 목록을 "이것 다음 몇 개"로 끊어 읽는 셈. 순수한 함수들이다.
 *
 * 댓글 목록은 쪽 번호가 아니라 이 방식이다. 마지막으로 받은 댓글의 번호(after)를 주면 그다음 것들을 돌려준다.
 * 읽는 사이에 새 댓글이 달려도 같은 댓글이 두 번 나오거나 빠지지 않는다. 대신 몇 쪽으로 건너뛸 수는 없다.
 * 댓글은 건너뛸 일이 없다. 위에서부터 이어 읽는다.
 *
 * 더 있는지는 하나를 더 읽어 보고 안다. size 개를 달라고 하면 size + 1 개를 읽는다.
 * 하나가 더 왔으면 뒤에 더 있는 것이고, 그 하나는 돌려주지 않는다.
 */

/** 적지 않았을 때 한 번에 담는 개수 */
export const DEFAULT_SLICE_SIZE = 20;
/** 한 번에 담을 수 있는 가장 큰 개수 */
export const MAX_SLICE_SIZE = 50;

/** 목록의 한 토막. */
export interface Slice<Item> {
  items: Item[];
  /** 다음 토막을 부를 때 after 에 넣을 값. 뒤에 더 없으면 null 이다 */
  next: string | null;
}

/** size 개를 돌려주려면 몇 개를 읽어야 하는가. 더 있는지 보려고 하나를 더 읽는다. */
export function fetchCount(size: number): number {
  return size + 1;
}

/**
 * 읽어 온 것(size + 1 개까지)을 토막으로 묶는다.
 *
 * idOf 는 항목의 번호를 꺼내는 함수다. 다음 토막은 마지막 항목의 번호 뒤부터다.
 */
export function sliceOf<Item>(
  fetched: Item[],
  size: number,
  idOf: (item: Item) => string,
): Slice<Item> {
  const items = fetched.slice(0, size);
  const hasMore = fetched.length > size;
  const last = items.at(-1);
  return {
    items,
    next: hasMore && last !== undefined ? idOf(last) : null,
  };
}
