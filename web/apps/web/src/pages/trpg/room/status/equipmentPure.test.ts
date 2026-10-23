// web/apps/web/src/pages/trpg/room/status/equipmentPure.test.ts
// 장비(#276)의 순수한 함수. 칸의 줄(여러 칸을 차지한 것은 한 줄), 공격과 방어, 착용할 칸, 바꿀 수 있는 때,
// 타격의 무기와 노릴 부위, 보내는 값, 결과의 타격 줄, 세이브 방식과 관통과 불굴 세이브를 본다.

import { describe, expect, it } from 'vitest';
import type { Round, Sheet, TableDetail, TableMember } from '../../../../api/types';
import { ME, member, RULES, round, sheet, tableDetail } from '../../../../test/tableFixtures';
import { actionHint, emptyActionDraft, toAction, type ActionDraft } from '../round/action/actionDraft';
import { myWeapons, strikeSlots, type ActionContext } from '../round/action/actionOptions';
import { actionLabel, blowLine } from '../round/roundView';
import { canChangeEquipment, defenseAt, equipmentNote, equipmentRows, fixedSlots, gearLabel, guardOf, wardOf, wearableItems } from './equipmentView';

const NPC = '00000000-0000-4000-8000-0000000000f1';
const SLOTS = [
  { key: 'main_hand', name: '주손', hit_weight: 0 },
  { key: 'off_hand', name: '보조손', hit_weight: 0 },
  { key: 'body', name: '몸', hit_weight: 3 },
  { key: 'head', name: '머리', hit_weight: 1 },
];
const ITEMS = [
  { entry_id: 'sword', name: '장검', kind: 'gear', rarity: 'normal', heals: null, slots: ['main_hand', 'off_hand'], slot_count: 2, attack: 2 },
  { entry_id: 'mail', name: '사슬 갑옷', kind: 'gear', rarity: 'normal', heals: null, slots: ['body'], slot_count: 1, defense: 4 },
  { entry_id: 'shield', name: '방패', kind: 'gear', rarity: 'normal', heals: null, slots: ['main_hand', 'off_hand'], slot_count: 1, guard: 1 },
  { entry_id: 'herb', name: '약초', kind: 'consumable', rarity: 'normal', heals: 'light', slots: [], slot_count: 1 },
  { entry_id: 'bolter', name: '볼터', kind: 'gear', rarity: 'normal', heals: null, slots: ['main_hand'], slot_count: 1, attack: 1, ap: 2 },
  { entry_id: 'halo', name: '헤일로', kind: 'gear', rarity: 'rare', heals: null, slots: ['head'], slot_count: 1, ward: 4 },
  { entry_id: 'charm', name: '부적', kind: 'gear', rarity: 'normal', heals: null, slots: ['off_hand'], slot_count: 1, ward: 2 },
];
const HELD = ITEMS.map((item) => ({ entry_id: item.entry_id, name: item.name, kind: item.kind, rarity: 'normal', count: 1 }));

function table(rules: Record<string, unknown> = {}, worn: unknown[] = [{ entry_id: 'sword', name: '장검', slots: ['main_hand', 'off_hand'] }]) {
  return tableDetail('t', {
    status: 'playing',
    rules: { ...RULES, equipment_slots: SLOTS, armor: { mode: 'ac' }, called_shot: { raise: 2 }, ...rules },
    items: ITEMS,
    members: [member(ME, { character: { name: '렌', description: '' }, sheet: sheet({ items: HELD, worn }) })],
  }) as unknown as TableDetail;
}

function mySheet(detail: TableDetail): Sheet {
  return detail.members[0]?.sheet as Sheet;
}

function ctx(detail: TableDetail): ActionContext {
  return { table: detail, me: detail.members[0] as TableMember, cast: null };
}

function harm(changes: Partial<ActionDraft>): ActionDraft {
  return { ...emptyActionDraft(RULES as unknown as TableDetail['rules']), kind: 'check', purpose: 'harm', target: `npc:${NPC}`, ...changes };
}

describe('장비의 줄', () => {
  it('규칙의 칸 차례로, 두 칸을 차지한 것은 한 줄, 빈 칸은 비어 있다', () => {
    const rows = equipmentRows(table(), mySheet(table()));
    expect(rows.map((row) => [row.label, row.worn?.name ?? null])).toEqual([
      ['주손·보조손', '장검'],
      ['몸', null],
      ['머리', null],
    ]);
  });

  it('공격과 방어는 판의 물건에서, 부위의 방어는 그 칸의 것과 모든 부위 방어의 합', () => {
    const worn = [
      { entry_id: 'mail', name: '사슬 갑옷', slots: ['body'] },
      { entry_id: 'shield', name: '방패', slots: ['off_hand'] },
    ];
    const detail = table({}, worn);
    expect(gearLabel(detail, 'sword')).toBe('공격 +2');
    expect(gearLabel(detail, 'shield')).toBe('모든 부위 +1');
    expect(gearLabel(detail, 'herb')).toBeNull();
    expect(guardOf(detail, mySheet(detail))).toBe(1);
    expect(defenseAt(detail, mySheet(detail), 'body')).toBe(5);
    expect(defenseAt(detail, mySheet(detail), 'head')).toBe(1);
  });

  it('착용할 물건은 칸이 있고 아직 착용하지 않은 것. 들어갈 칸이 정해져 있으면 고르지 않는다', () => {
    const detail = table();
    expect(wearableItems(detail, mySheet(detail)).map((item) => item.entry_id)).toEqual(['mail', 'shield', 'bolter', 'halo', 'charm']);
    expect(fixedSlots(detail, 'sword')).toEqual(['main_hand', 'off_hand']);
    expect(fixedSlots(detail, 'mail')).toEqual(['body']);
    expect(fixedSlots(detail, 'shield')).toBeNull();
  });

  it('진행 중이고 선언을 받는 중이며 서 있을 때만 바꾼다', () => {
    const detail = table();
    const me = detail.members[0] as TableMember;
    const open = round(2) as unknown as Round;
    expect(canChangeEquipment(detail, me, open)).toBe(true);
    expect(canChangeEquipment(detail, me, { ...open, status: 'closing' })).toBe(false);
    expect(canChangeEquipment(detail, { ...me, sheet: { ...(me.sheet as Sheet), hp: 0 } }, open)).toBe(false);
    expect(canChangeEquipment(detail, me, undefined)).toBe(false);
  });
});

describe('타격의 무기와 부위', () => {
  it('무기는 착용한 것 중 공격 보정이 있는 것, 부위는 방어 방식과 노려 치기가 있을 때 맞을 수 있는 칸', () => {
    expect(myWeapons(ctx(table()))).toEqual([{ value: 'sword', label: '장검(+2)' }]);
    expect(strikeSlots(ctx(table())).map((slot) => slot.value)).toEqual(['body', 'head']);
    expect(strikeSlots(ctx(table({ armor: null })))).toEqual([]);
    expect(strikeSlots(ctx(table({ called_shot: null })))).toEqual([]);
  });

  it('무기와 부위를 보내고, 부위를 노리면 부상은 보내지 않는다. 둘 다 고르면 알린다', () => {
    const c = ctx(table());
    expect(toAction(harm({ weapon: 'sword', strike: 'body' }), c)).toMatchObject({ weapon: 'sword', strike: 'body', npc: NPC });
    expect(toAction(harm({ strike: 'body', aim: 'broken_arm' }), c)).not.toHaveProperty('aim');
    expect(toAction(harm({}), c)).not.toHaveProperty('weapon');
    expect(actionHint(harm({ strike: 'body', aim: 'broken_arm' }), c)).toContain('하나만');
  });

  it('행동과 결과의 글', () => {
    const detail = table();
    const action = { kind: 'check', ability: 'str', difficulty: 'normal', harm: 'light', lethal: false, npc: NPC, weapon: 'sword', strike: 'body' } as const;
    expect(actionLabel(action, detail)).toBe('판정 · 근력, 보통, 공격, 장검, 몸 노림');
    const blow = { weapon: { entry_id: 'sword', name: '장검', bonus: 2, ap: 0 }, location: 'body', location_name: '몸', aimed: true, defense: 5, mode: 'ac' };
    expect(blowLine(blow)).toBe('장검 +2 · 몸(노림) · 방어 5(목표값에 더함)');
    expect(blowLine({ ...blow, weapon: null, aimed: false, mode: 'reduce', defense: 2 })).toBe('몸 · 방어 2(피해에서 뺌)');
    expect(blowLine(null)).toBeNull();
  });
});

describe('세이브와 관통', () => {
  const SAVE = { armor: { mode: 'save', save_target: 7, pierce_base: 10 } };
  const worn = [
    { entry_id: 'bolter', name: '볼터', slots: ['main_hand'] },
    { entry_id: 'charm', name: '부적', slots: ['off_hand'] },
    { entry_id: 'halo', name: '헤일로', slots: ['head'] },
    { entry_id: 'mail', name: '사슬 갑옷', slots: ['body'] },
  ];

  it('물건에 관통력과 불굴 세이브를 적고, 불굴 세이브는 더하지 않고 가장 큰 값이다', () => {
    const detail = table(SAVE, worn);
    expect(gearLabel(detail, 'bolter')).toBe('공격 +1 · 관통 2');
    expect(gearLabel(detail, 'halo')).toBe('불굴 세이브 4');
    expect(wardOf(detail, mySheet(detail))).toBe(4);
    expect(wardOf(table(SAVE, []), mySheet(table(SAVE, [])))).toBe(0);
  });

  it('장비 아래 줄에 불굴 세이브와 세이브의 목표값을 적는다. 적을 것이 없으면 null', () => {
    const detail = table(SAVE, worn);
    expect(equipmentNote(detail, mySheet(detail))).toBe('불굴 세이브 4 · 방어는 세이브로 막음(목표 7)');
    expect(equipmentNote(table(), mySheet(table()))).toBe('방어는 맞히기 어렵게');
    expect(equipmentNote(table({ armor: null }, []), mySheet(table({ armor: null }, [])))).toBeNull();
  });

  it('무기 고르기에 관통력을 붙인다', () => {
    expect(myWeapons(ctx(table(SAVE, worn)))).toEqual([{ value: 'bolter', label: '볼터(+1, 관통 2)' }]);
  });

  it('타격 줄에 관통과 세이브. 관통했거나 세이브 방식이면 방어가 한 일을 붙이지 않는다', () => {
    const blow = {
      weapon: { entry_id: 'bolter', name: '볼터', bonus: 1, ap: 2 },
      location: 'body',
      location_name: '몸',
      aimed: false,
      defense: 5,
      mode: 'save',
      pierce: { roll: 9, ap: 2, target: 15, pierced: false },
      save: { kind: 'armor', value: 5, roll: 10, target: 7, saved: true },
    };
    expect(blowLine(blow)).toBe('볼터 +1 · 몸 · 방어 5 · 관통 못 함 · 아머 세이브 10 + 5 → 막음');
    const pierced = { ...blow, pierce: { roll: 14, ap: 2, target: 15, pierced: true }, save: { kind: 'ward', value: 4, roll: 2, target: 7, saved: false } };
    expect(blowLine(pierced)).toBe('볼터 +1 · 몸 · 방어 5 · 관통함 · 불굴 세이브 2 + 4 → 못 막음');
    expect(blowLine({ ...pierced, mode: 'ac', save: null })).toBe('볼터 +1 · 몸 · 방어 5 · 관통함');
    expect(blowLine({ weapon: null, location: null, location_name: null, aimed: false, defense: 0, mode: 'save', save: blow.save })).toBe(
      '아머 세이브 10 + 5 → 막음',
    );
  });
});
