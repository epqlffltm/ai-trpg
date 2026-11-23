// web/apps/web/src/pages/trpg/room/leaveGuardView.test.ts
// 떠나기 전의 물음(#1344)이 물을지 정하는 순수한 함수. 다른 곳으로 가면 묻고, 같은 방 안에서 옮기거나 이미 나갔으면 묻지 않는다.

import type { Location } from 'react-router';
import { describe, expect, it } from 'vitest';
import { LEFT_TABLE, shouldAsk } from './leaveGuardView';

const ROOM = '/trpg/tables/t1';

function at(pathname: string, state: unknown = null): Location {
  return { pathname, search: '', hash: '', state, key: pathname };
}

describe('떠나기 전에 물을까', () => {
  it('방 밖으로 가면 묻는다', () => {
    expect(shouldAsk('t1', at(ROOM), at('/board'))).toBe(true);
    expect(shouldAsk('t1', at(ROOM), at('/trpg/tables/t10'))).toBe(true);
  });

  it('같은 방 안에서 옮기거나 같은 곳이면 묻지 않는다', () => {
    expect(shouldAsk('t1', at(ROOM), at(`${ROOM}/story`))).toBe(false);
    expect(shouldAsk('t1', at(ROOM), at(ROOM))).toBe(false);
  });

  it('나가기 단추로 이미 나갔으면 묻지 않는다', () => {
    expect(shouldAsk('t1', at(ROOM), at('/trpg/lobby', LEFT_TABLE))).toBe(false);
  });
});
