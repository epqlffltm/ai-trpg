// web/apps/web/src/pages/trpg/room/host/hostPure.test.ts
// 방장의 운영의 순수한 함수. "한 번 더 굴리기"를 보일 때, 고를 거리에 지금 값 넣기, 실패의 글을 본다.

import { describe, expect, it } from 'vitest';
import { ApiError } from '../../../../api/errors';
import type { TableDetail, TableMember } from '../../../../api/types';
import { ME, member, OTHER, roll, sheet, tableDetail } from '../../../../test/tableFixtures';
import { describeHostProblem } from './hostProblem';
import { canGrantReroll, otherMembers } from './hostView';
import { withCurrent } from './TableSettings';

function table(extra: Record<string, unknown> = {}): TableDetail {
  return tableDetail('t', extra) as unknown as TableDetail;
}

function asMember(extra: Record<string, unknown>): TableMember {
  return member(OTHER, extra) as unknown as TableMember;
}

describe('canGrantReroll', () => {
  it('허락한 테이블에서, 지금 캐릭터를 위해 굴렸고 아직 받지 않은 사람에게', () => {
    expect(canGrantReroll(table(), asMember({ roll: roll([15, 12, 9]) }))).toBe(true);
    expect(canGrantReroll(table(), asMember({ roll: roll([15, 12, 9], { reroll_granted: true }) }))).toBe(false);
    expect(canGrantReroll(table(), asMember({}))).toBe(false);
    expect(canGrantReroll(table({ reroll_allowed: false }), asMember({ roll: roll([15, 12, 9]) }))).toBe(false);
    expect(canGrantReroll(table({ character_modes: ['pregen'] }), asMember({ roll: roll([15, 12, 9]) }))).toBe(false);
  });

  it('진행 중에는 캐릭터가 죽어 새 캐릭터를 굴린 사람에게만', () => {
    const playing = table({ status: 'playing' });
    const fresh = roll([15, 12, 9], { character_number: 2 });
    expect(canGrantReroll(playing, asMember({ sheet: sheet({ dead: true, hp: 0 }), roll: fresh }))).toBe(true);
    expect(canGrantReroll(playing, asMember({ sheet: sheet(), roll: fresh }))).toBe(false);
  });
});

describe('hostView', () => {
  it('나를 뺀 앉은 사람들', () => {
    expect(otherMembers(table(), ME).map((entry) => entry.user_id)).toEqual([OTHER]);
  });

  it('고를 거리에 지금 값이 없으면 넣는다', () => {
    expect(withCurrent([60, 300], 300)).toEqual([60, 300]);
    expect(withCurrent<number | null>([60, null], 90)).toEqual([60, null, 90]);
  });
});

describe('describeHostProblem', () => {
  it('방장이 아니면, 그 사람이 없으면, 끝났으면 다시 읽는다. 참고 자료의 422 는 허용하지 않는 판이다', () => {
    expect(describeHostProblem(new ApiError({ status: 403, detail: 'x' }))).toMatchObject({ refresh: true });
    expect(describeHostProblem(new ApiError({ status: 404, detail: 'x' })).message).toBe('그 사람은 이미 테이블에 없습니다.');
    expect(describeHostProblem(new ApiError({ status: 409, detail: 'x', code: 'cannot_kick_self' })).message).toContain('나가기');
    const references = new ApiError({ status: 422, detail: 'references_enabled 에 고를 수 없는 값이 있습니다.' });
    expect(describeHostProblem(references).message).toBe('이 시나리오는 참고 자료를 허용하지 않습니다.');
  });
});
