// web/apps/web/src/pages/trpg/room/round/action/actionPure.test.ts
// 선언의 행동(③-2)의 순수한 함수. 고를 수 있는 종류와 대상, 보내는 값(서버의 action.py 의 칸), 보내기 전의 검사를 본다.

import { describe, expect, it } from 'vitest';
import type { SceneCast, TableDetail, TableMember } from '../../../../../api/types';
import { ME, member, OTHER, RULES, sheet, tableDetail } from '../../../../../test/tableFixtures';
import { actionHint, draftFromAction, emptyActionDraft, toAction, type ActionDraft } from './actionDraft';
import { throwTerms } from './ItemActionFields';
import {
  aidItems,
  availableKinds,
  carriable,
  harmTargets,
  patients,
  recipients,
  throwables,
  treatableInjuries,
  victims,
  type ActionContext,
} from './actionOptions';

const THIRD = '00000000-0000-4000-8000-0000000000e3';
const NPC = '00000000-0000-4000-8000-0000000000f1';
const MONSTER = '00000000-0000-4000-8000-0000000000f2';
const FAR_MONSTER = '00000000-0000-4000-8000-0000000000f3';

const HERB = { entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', count: 3 };
const ROPE = { entry_id: 'i2', name: '밧줄', kind: 'gear', rarity: 'normal', count: 1 };

function context(mySheet: Record<string, unknown> = {}, rules: Record<string, unknown> = {}, cast: SceneCast | null = CAST): ActionContext {
  const table = tableDetail('t', {
    status: 'playing',
    rules: { ...RULES, ...rules },
    members: [
      member(ME, { character: { name: '렌', description: '' }, sheet: sheet({ place_id: 'p1', items: [HERB, ROPE], ...mySheet }) }),
      member(OTHER, {
        character: { name: '미아', description: '' },
        sheet: sheet({ place_id: 'p1', hp: 0, injuries: [{ injury: 'broken_arm', round: 1, ends_after_round: null, heals_at: null }] }),
      }),
      member(THIRD, { character: { name: '조', description: '' }, sheet: sheet({ place_id: 'p2', dead: true, hp: 0 }) }),
    ],
    items: [
      { entry_id: 'i1', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light' },
      { entry_id: 'i3', name: '연막탄', kind: 'consumable', rarity: 'normal', heals: null },
    ],
    map: {
      places: [
        { entry_id: 'p1', name: '수도원 문', items: [{ entry_id: 'i4', name: '횃불', count: 2 }] },
        { entry_id: 'p2', name: '부엌', items: [] },
      ],
      routes: [{ from_place: 'p1', to_place: 'p2', travel_minutes: 5, two_way: true }],
    },
  }) as unknown as TableDetail;
  return { table, me: table.members[0] as TableMember, cast };
}

const CAST = {
  round: 2,
  people: [
    { id: NPC, name: '문지기', named: false, status: 'alive', injuries: ['broken_arm'], attitude: 'wary', items: [{ entry_id: 'i5', name: '열쇠', rarity: 'rare', count: 1, equipped: false }] },
  ],
  monsters: [
    {
      id: MONSTER,
      name: '수로 쥐',
      place_id: 'p1',
      status: 'downed',
      condition: '쓰러짐',
      items: [{ entry_id: 'i6', name: '반지', rarity: 'normal', count: 1, equipped: true }],
      injuries: ['broken_arm'],
    },
    { id: FAR_MONSTER, name: '박쥐', place_id: 'p2', status: 'alive', condition: '멀쩡함', items: [], injuries: [] },
  ],
} as unknown as SceneCast;

function draft(changes: Partial<ActionDraft>): ActionDraft {
  return { ...emptyActionDraft(RULES as unknown as TableDetail['rules']), ...changes };
}

describe('availableKinds', () => {
  it('규칙과 내 시트, 맵, 장면에 따라 고를 수 있는 종류가 달라진다', () => {
    expect(availableKinds(context())).toEqual(['check', 'name', 'use', 'give', 'move', 'search', 'take', 'put_down', 'loot', 'wait']);
    const full = context({}, { treatment: { ability: 'wis' }, rest: { short: { minutes: 60 }, long: { minutes: 480 } }, steal: { ability: 'dex' } });
    expect(availableKinds(full)).toEqual(expect.arrayContaining(['treat', 'steal', 'rest']));
  });

  it('쓰러졌거나 죽었으면 행동을 붙이지 못한다', () => {
    expect(availableKinds(context({ hp: 0 }))).toEqual([]);
    expect(availableKinds(context({ dead: true }))).toEqual([]);
  });

  it('장면을 아직 읽지 못했으면 대상이 필요한 행동은 빠진다', () => {
    expect(availableKinds(context({}, {}, null))).not.toContain('loot');
  });
});

describe('actionOptions', () => {
  it('받을 사람은 살아 있는 다른 사람이다. 업고 갈 사람은 같은 곳에 쓰러진 사람이다', () => {
    const ctx = context();
    expect(recipients(ctx)).toEqual([{ value: `member:${OTHER}`, label: '미아' }]);
    expect(carriable(ctx)).toEqual([{ value: OTHER, label: '미아' }]);
  });

  it('칠 대상은 장면의 산 인물과 내가 선 곳의 몬스터다', () => {
    expect(harmTargets(context()).map((choice) => choice.value)).toEqual([`npc:${NPC}`, `monster:${MONSTER}`]);
  });

  it('몬스터는 몸 상태와 입은 부상의 이름으로 보인다', () => {
    expect(harmTargets(context()).find((choice) => choice.value === `monster:${MONSTER}`)?.label).toBe('수로 쥐(쓰러짐 · 부러진 팔)');
  });

  it('훔치기는 쓰러지지 않은, 빼앗기는 쓰러지거나 죽은, 물건을 지닌 대상이다', () => {
    expect(victims(context(), 'steal').map((choice) => choice.value)).toEqual([`npc:${NPC}`]);
    expect(victims(context(), 'loot').map((choice) => choice.value)).toEqual([`monster:${MONSTER}`]);
  });

  it('치료할 부상은 그 쪽이 입은 오래 가는 부상이다', () => {
    const ctx = context();
    expect(patients(ctx).map((choice) => choice.value)).toEqual(['', `member:${OTHER}`, `npc:${NPC}`]);
    expect(treatableInjuries(ctx, `member:${OTHER}`)).toEqual([{ value: 'broken_arm', label: '부러진 팔' }]);
    expect(treatableInjuries(ctx, '')).toEqual([]);
  });
});

describe('toAction', () => {
  const ctx = context();

  it('판정은 목적에 맞는 칸만 보낸다. 노려 치기는 인물과 몬스터에게', () => {
    expect(toAction(draft({ kind: 'check', risk: 'light' }), ctx)).toEqual({ kind: 'check', ability: 'str', difficulty: 'normal', risk: 'light', lethal: false });
    expect(toAction(draft({ kind: 'check', purpose: 'harm', target: `npc:${NPC}`, magnitude: 'heavy', lethal: true, aim: 'broken_arm' }), ctx)).toEqual({
      kind: 'check',
      ability: 'str',
      difficulty: 'normal',
      harm: 'heavy',
      lethal: true,
      npc: NPC,
      aim: 'broken_arm',
    });
    expect(toAction(draft({ kind: 'check', purpose: 'harm', target: `monster:${MONSTER}`, aim: 'broken_arm' }), ctx)).toEqual({
      kind: 'check',
      ability: 'str',
      difficulty: 'normal',
      harm: 'light',
      lethal: false,
      monster: MONSTER,
      aim: 'broken_arm',
    });
    expect(toAction(draft({ kind: 'check', purpose: 'recover', target: `member:${OTHER}` }), ctx)).toMatchObject({ recover: 'light', target: OTHER });
  });

  it('물건 쓰기는 회복하는 소모품일 때만 받을 사람을 보낸다', () => {
    expect(toAction(draft({ kind: 'use', item: 'i1', target: `member:${OTHER}` }), ctx)).toEqual({ kind: 'use', item: 'i1', target: OTHER });
    expect(toAction(draft({ kind: 'use', item: 'i3', target: `member:${OTHER}` }), ctx)).toEqual({ kind: 'use', item: 'i3' });
  });

  it('건네기, 가기, 줍기, 빼앗기, 치료, 지목, 쉬기, 기다리기의 칸', () => {
    expect(toAction(draft({ kind: 'give', item: 'i1', count: 2, target: `member:${OTHER}` }), ctx)).toEqual({ kind: 'give', item: 'i1', count: 2, target: OTHER });
    expect(toAction(draft({ kind: 'move', place: 'p2', carry: OTHER }), ctx)).toEqual({ kind: 'move', place: 'p2', carry: OTHER });
    expect(toAction(draft({ kind: 'take', item: 'i4', count: 9 }), ctx)).toEqual({ kind: 'take', item: 'i4', count: 2 });
    expect(toAction(draft({ kind: 'loot', target: `monster:${MONSTER}`, item: 'i6' }), ctx)).toEqual({ kind: 'loot', item: 'i6', monster: MONSTER });
    expect(toAction(draft({ kind: 'treat', injury: 'broken_arm', target: `member:${OTHER}` }), ctx)).toEqual({ kind: 'treat', injury: 'broken_arm', target: OTHER });
    expect(toAction(draft({ kind: 'name', guess: ' 마르타 ', npc: NPC }), ctx)).toEqual({ kind: 'name', name: '마르타', npc: NPC });
    expect(toAction(draft({ kind: 'rest', length: 'long' }), ctx)).toEqual({ kind: 'rest', length: 'long' });
    expect(toAction(draft({ kind: 'wait', minutes: 30 }), ctx)).toEqual({ kind: 'wait', minutes: 30 });
    expect(toAction(draft({ kind: 'none' }), ctx)).toBeNull();
  });

  it('낸 행동으로 채우면 같은 것을 다시 보낸다', () => {
    const sent = { kind: 'check', ability: 'dex', difficulty: 'easy', harm: 'heavy', lethal: false, npc: NPC } as const;
    expect(toAction(draftFromAction(RULES as unknown as TableDetail['rules'], sent), ctx)).toEqual(sent);
    const give = { kind: 'give', item: 'i1', count: 2, target: OTHER } as const;
    expect(toAction(draftFromAction(RULES as unknown as TableDetail['rules'], give), ctx)).toEqual(give);
  });

  it('사기, 팔기, 돈 건네기도 낸 것을 그대로 다시 보낸다(#278)', () => {
    const rules = RULES as unknown as TableDetail['rules'];
    const buy = { kind: 'buy', npc: NPC, item: 'i1', count: 2 } as const;
    const sell = { kind: 'sell', npc: NPC, item: 'i1', count: 1 } as const;
    const pay = { kind: 'pay', target: OTHER, amount: 30 } as const;
    expect(toAction(draftFromAction(rules, buy), ctx)).toEqual(buy);
    expect(toAction(draftFromAction(rules, sell), ctx)).toEqual(sell);
    expect(toAction(draftFromAction(rules, pay), ctx)).toEqual(pay);
    expect(actionHint(draft({ kind: 'buy', item: 'i1' }), ctx)).toBe('상인과 물건을 골라 주세요.');
    expect(actionHint(draft({ kind: 'pay', target: `member:${OTHER}`, amount: 0 }), ctx)).toContain('1에서');
  });

  it('자물쇠 바꾸기는 문과 달 자물쇠를 보내고, 낸 것을 그대로 다시 보낸다(#281)', () => {
    const replace = { kind: 'replace', place: 'p2', item: 'i1' } as const;
    expect(toAction(draft({ kind: 'replace', place: 'p2', item: 'i1' }), ctx)).toEqual(replace);
    expect(toAction(draftFromAction(RULES as unknown as TableDetail['rules'], replace), ctx)).toEqual(replace);
    expect(actionHint(draft({ kind: 'replace', place: 'p2' }), ctx)).toBe('다룰 문과 달 자물쇠를 골라 주세요.');
    expect(actionHint(draft({ kind: 'replace', place: 'p2', item: 'i1' }), ctx)).toBeNull();
  });

  it('던지기는 물건과 맞힐 대상과 죽이려는지만 보내고, 낸 것을 그대로 다시 보낸다(#277)', () => {
    const rules = RULES as unknown as TableDetail['rules'];
    const atMonster = { kind: 'throw', item: 'i7', lethal: true, monster: MONSTER } as const;
    const atNpc = { kind: 'throw', item: 'i7', lethal: false, npc: NPC } as const;
    expect(toAction(draft({ kind: 'throw', item: 'i7', target: `monster:${MONSTER}`, lethal: true, ability: 'str' }), ctx)).toEqual(atMonster);
    expect(toAction(draftFromAction(rules, atMonster), ctx)).toEqual(atMonster);
    expect(toAction(draftFromAction(rules, atNpc), ctx)).toEqual(atNpc);
    expect(actionHint(draft({ kind: 'throw', item: 'i7' }), ctx)).toBe('던질 물건과 맞힐 대상을 골라 주세요.');
    expect(actionHint(draft({ kind: 'throw', item: 'i7', target: `npc:${NPC}` }), ctx)).toBeNull();
  });
});

describe('aidItems', () => {
  const KIT = { entry_id: 'i8', name: '의료 키트', kind: 'consumable', rarity: 'normal', count: 2 };

  function withKit(): ActionContext {
    const base = context({ items: [HERB, KIT] });
    const kit = { entry_id: 'i8', name: '의료 키트', kind: 'consumable', rarity: 'normal', heals: null, treat_bonus: 2 };
    return { ...base, table: { ...base.table, items: [...base.table.items, kit] } as unknown as TableDetail };
  }

  it('치료 보정이 있는 물건만 붙여 쓸 수 있고, 치료에 붙여 보낸다(#277)', () => {
    const ctx = withKit();
    expect(aidItems(ctx)).toEqual([{ value: 'i8', label: '의료 키트 +2 ×2' }]);
    const aided = { kind: 'treat', injury: 'broken_arm', target: OTHER, item: 'i8' } as const;
    expect(toAction(draft({ kind: 'treat', injury: 'broken_arm', target: `member:${OTHER}`, item: 'i8' }), ctx)).toEqual(aided);
    expect(toAction(draftFromAction(RULES as unknown as TableDetail['rules'], aided), ctx)).toEqual(aided);
    // 다른 종류에서 고른 물건(약초)이 남아 있어도 치료에는 붙이지 않는다
    expect(toAction(draft({ kind: 'treat', injury: 'broken_arm', item: 'i1' }), ctx)).toEqual({ kind: 'treat', injury: 'broken_arm' });
  });
});

describe('throwables', () => {
  const FIREBOMB = { entry_id: 'i7', name: '화염병', kind: 'consumable', rarity: 'normal', count: 2 };

  function withFirebomb(cast: SceneCast | null = CAST): ActionContext {
    const base = context({ items: [HERB, FIREBOMB] }, {}, cast);
    const thrown = { entry_id: 'i7', name: '화염병', kind: 'consumable', rarity: 'normal', heals: null, throw: { ability: 'dex', difficulty: null, harm: 'light' } };
    return { ...base, table: { ...base.table, items: [...base.table.items, thrown] } as unknown as TableDetail };
  }

  it('던지는 판정이 있는 물건을 지녔고 칠 대상이 있으면 던지기를 고를 수 있다', () => {
    expect(throwables(withFirebomb()).map((item) => item.entry_id)).toEqual(['i7']);
    expect(availableKinds(withFirebomb())).toContain('throw');
    expect(availableKinds(context())).not.toContain('throw');
    expect(availableKinds(withFirebomb({ round: 2, people: [], monsters: [] } as unknown as SceneCast))).not.toContain('throw');
  });

  it('물건에 적힌 판정을 보인다. 난이도를 비웠으면 규칙의 기본이다', () => {
    const terms = throwTerms(withFirebomb().table, 'i7');
    expect(terms).toContain('맞든 빗나가든 하나 없어집니다');
    expect(throwTerms(withFirebomb().table, 'i1')).toBeNull();
  });
});

describe('actionHint', () => {
  const ctx = context();

  it('고를 것을 고르지 않았거나 개수와 시간이 범위를 넘으면 알린다', () => {
    expect(actionHint(draft({ kind: 'give', item: 'i1' }), ctx)).toBe('건넬 물건과 받을 사람을 골라 주세요.');
    expect(actionHint(draft({ kind: 'give', item: 'i1', target: `member:${OTHER}`, count: 4 }), ctx)).toBe('개수는 3개까지입니다.');
    expect(actionHint(draft({ kind: 'check', purpose: 'harm' }), ctx)).toBe('칠 대상을 골라 주세요.');
    expect(actionHint(draft({ kind: 'wait', minutes: 0 }), ctx)).toContain('1분에서');
    expect(actionHint(draft({ kind: 'name', guess: '  ' }), ctx)).toBe('짚을 이름을 적어 주세요.');
    expect(actionHint(draft({ kind: 'search' }), ctx)).toBeNull();
  });
});
