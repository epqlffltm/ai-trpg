// board-server/src/comments/slice.spec.ts

/**
 * 목록을 "이것 다음 몇 개"로 끊어 읽는 셈(slice.ts)을 검증한다.
 */

import { fetchCount, sliceOf } from './slice.js';

/** 번호만 있는 항목들을 만든다. */
function items(...ids: string[]): { id: string }[] {
  return ids.map((id) => ({ id }));
}

const idOf = (item: { id: string }): string => item.id;

describe('fetchCount', () => {
  it('더 있는지 보려고 하나를 더 읽는다', () => {
    expect(fetchCount(20)).toBe(21);
  });
});

describe('sliceOf', () => {
  it('하나가 더 왔으면 뒤에 더 있다. 그 하나는 돌려주지 않는다', () => {
    const slice = sliceOf(items('1', '2', '3'), 2, idOf);

    expect(slice).toEqual({ items: items('1', '2'), next: '2' });
  });

  it('딱 맞게 왔으면 뒤에 더 없다', () => {
    const slice = sliceOf(items('1', '2'), 2, idOf);

    expect(slice).toEqual({ items: items('1', '2'), next: null });
  });

  it('모자라게 왔으면 뒤에 더 없다', () => {
    const slice = sliceOf(items('1'), 2, idOf);

    expect(slice).toEqual({ items: items('1'), next: null });
  });

  it('아무것도 없으면 빈 토막이다', () => {
    expect(sliceOf([], 2, idOf)).toEqual({ items: [], next: null });
  });
});
