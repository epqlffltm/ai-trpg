// web/apps/web/src/pages/trpg/room/round/action/Defend.test.tsx
// 방어하기(#254)를 본다. 늘 고를 수 있고, 고르면 {kind: 'defend'} 를 보낸다. 결과에는 방어 태세가 보인다.

import { describe, expect, it } from 'vitest';
import type { TableDetail } from '../../../../../api/types';
import { ME, member, RULES, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { outcomeLine } from '../roundView';
import { ACTION_LABELS } from './actionLabels';
import { toAction } from './actionDraft';
import { availableKinds } from './actionOptions';

const TABLE_ID = '00000000-0000-4000-8000-0000000000ed';

function playing() {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    rules: RULES,
    members: [member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet() })],
  }) as unknown as TableDetail;
}

function ctx(table: TableDetail) {
  return { table, me: table.members[0] as TableDetail['members'][number], cast: null };
}

describe('방어하기', () => {
  it('늘 고를 수 있고, 고를 것 없이 보낸다', () => {
    const table = playing();
    expect(availableKinds(ctx(table))).toContain('defend');
    expect(ACTION_LABELS.defend).toBe('방어하기');
    expect(toAction({ kind: 'defend', target: '' } as unknown as Parameters<typeof toAction>[0], ctx(table))).toEqual({ kind: 'defend' });
  });

  it('결과에 방어 태세가 보인다', () => {
    expect(outcomeLine({ defend: { guarded: true } } as Parameters<typeof outcomeLine>[0], playing().rules)).toBe(
      '방어 태세: 이 라운드에 나를 노린 공격이 불리했습니다.',
    );
  });
});
