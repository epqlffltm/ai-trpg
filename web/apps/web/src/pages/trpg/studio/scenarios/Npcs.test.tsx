// web/apps/web/src/pages/trpg/studio/scenarios/Npcs.test.tsx
// 시나리오의 인물 탭(B9). 기본 인물 시트를 탭의 저장으로, 인물 시트(태도, 상인, 장비와 착용·떨어질 확률, 소지품, 공격과 무기)를
// 창에서 바로 보내기, 시트 지우기, 로어북의 인물이 아닌 것의 시트, 한편인 몬스터(#254).
// 입력의 순수한 함수(장비·소지품의 겹침, 공격, 빈 시트, 한편 고르기).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { ItemRule, NpcSheet, Ruleset } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { defaultDefense } from './AttacksEditor';
import { attackDrafts, attacksHints, toAttacks } from './attacksForm';
import { allyChoices, hasNpcHints, npcDraft, npcHints, npcLine, withAlly } from './npcForm';
import { problemLine } from './publishProblems';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GUARD = '00000000-0000-4000-8000-00000000b001';
const MONK = '00000000-0000-4000-8000-00000000b002';
const GONE = '00000000-0000-4000-8000-00000000b003';
const SWORD = '00000000-0000-4000-8000-00000000a001';
const BREAD = '00000000-0000-4000-8000-00000000a002';
const BESTIARY = '00000000-0000-4000-8000-0000000000d4';
const GHOUL = '00000000-0000-4000-8000-00000000c001';
const LICH = '00000000-0000-4000-8000-00000000c002';
const rules = RULES as unknown as Ruleset;

const SWORD_RULE = { entry_id: SWORD, kind: 'gear', rarity: 'normal', effects: [], price: 10, slots: ['main_hand'], slot_count: 1, attack: 2, ap: null, defense: null, guard: null, ward: null, aids: [], resistances: [] };

const MONK_SHEET = {
  entry_id: MONK,
  sheet: { abilities: { str: 8, dex: 10, con: 10 }, max_hp: 6 },
  attitude: 'friendly',
  equipment: [],
  inventory: [{ entry_id: BREAD, count: 3, chance: 100, wear: [] }],
  dull: false,
  on_caught: 'hostile',
  attacks: [],
  merchant: true,
  allied_monsters: [],
};

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function scenario(extra: Record<string, unknown> = {}) {
  return scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    openings: ['종이 울린다.'],
    character_modes: ['pregen'],
    npc_sheets: [MONK_SHEET, { ...MONK_SHEET, entry_id: GONE, inventory: [], merchant: false }],
    items: [SWORD_RULE],
    ...extra,
  });
}

function monster(id: string, name: string) {
  return { id, name, kind: 'undead', content: '', unique: false, created_at: '', updated_at: '' };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenario(start);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [entry(GUARD, '늙은 문지기', 'person'), entry(MONK, '수도사', 'person'), entry(SWORD, '녹슨 검', 'item'), entry(BREAD, '검은 빵', 'item')]),
    [`GET ${GAME}/bestiaries/${BESTIARY}/monsters`]: () => json(200, [monster(GHOUL, '구울'), monster(LICH, '리치')]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  });
}

function patches(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as Record<string, unknown>);
}

async function npcsPanel() {
  return within(await screen.findByRole('tabpanel', { name: '인물' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('인물 탭', () => {
  it('기본 인물 시트를 탭의 저장으로 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=npcs`);

    const form = within(await (await npcsPanel()).findByRole('form', { name: '인물' }));
    for (const [name, value] of [['근력', '10'], ['민첩', '10'], ['건강', '10'], ['최대 HP', '8']]) {
      await userEvent.type(form.getByRole('textbox', { name }), value as string);
    }
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)[0]).toEqual({ default_npc_sheet: { abilities: { str: 10, dex: 10, con: 10 }, max_hp: 8 } });
  });

  it('인물마다 시트를 창에서 적으면 목록을 통째로 보낸다. 무기는 장비의 물건이다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=npcs`);

    const list = within(await (await npcsPanel()).findByRole('list', { name: '인물 시트' }));
    expect(list.getByText('시트 없음(기본 인물 시트)')).toBeInTheDocument();
    expect(list.getByText('근력 8 · 민첩 10 · 건강 10 · HP 6 · 우호 · 상인 · 소지품 1')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '늙은 문지기 시트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText(/인물 시트에는 숫자가 있어야 합니다/)).toBeInTheDocument();
    for (const [name, value] of [['근력', '14'], ['민첩', '10'], ['건강', '12'], ['최대 HP', '12']]) {
      await userEvent.type(dialog.getByRole('textbox', { name }), value as string);
    }
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '처음 태도' }), 'wary');
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '훔치다 들키면' }), 'fight');

    await userEvent.click(dialog.getByRole('button', { name: '장비 더하기' }));
    const gear = within(dialog.getByRole('group', { name: '장비 1' }));
    expect(gear.getByRole('combobox', { name: '물건' })).toHaveValue(SWORD);
    await userEvent.click(gear.getByRole('checkbox', { name: '주손' }));
    await userEvent.clear(gear.getByRole('textbox', { name: '떨어질 확률(%)' }));
    await userEvent.type(gear.getByRole('textbox', { name: '떨어질 확률(%)' }), '50');

    await userEvent.click(dialog.getByRole('button', { name: '소지품 더하기' }));
    const bag = within(dialog.getByRole('group', { name: '소지품 1' }));
    expect(bag.queryByRole('checkbox')).toBeNull();
    expect(bag.getByText('장비와 소지품에 같은 물건이 있습니다. 한쪽에만 적어 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(bag.getByRole('combobox', { name: '물건' }), BREAD);

    await userEvent.click(dialog.getByRole('button', { name: '공격 더하기' }));
    const attack = within(dialog.getByRole('group', { name: '공격 1' }));
    await userEvent.type(attack.getByRole('textbox', { name: '이름' }), '검 휘두르기');
    await userEvent.selectOptions(attack.getByRole('combobox', { name: '무기' }), SWORD);
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const sent = patches(seen)[0]?.npc_sheets as NpcSheet[];
    expect(sent.map((npc) => npc.entry_id)).toEqual([MONK, GONE, GUARD]);
    expect(sent[2]).toEqual({
      entry_id: GUARD,
      sheet: { abilities: { str: 14, dex: 10, con: 12 }, max_hp: 12 },
      attitude: 'wary',
      dull: false,
      on_caught: 'fight',
      merchant: false,
      equipment: [{ entry_id: SWORD, count: 1, chance: 50, wear: ['main_hand'] }],
      inventory: [{ entry_id: BREAD, count: 1, chance: 100, wear: [] }],
      attacks: [{ name: '검 휘두르기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: SWORD, cost: null, effects: [], nature: null, defense: null }],
      resistances: [],
      nature: null,
      allied_monsters: [],
      defends: null,
    });
  });

  it('한편인 몬스터를 시트를 적은 몬스터 가운데서 고르고, 시트가 없는 것은 뺄 수 있게 남긴다', async () => {
    const ghoulSheet = {
      monster_id: GHOUL,
      sheet: { abilities: { str: 14, dex: 10, con: 12 }, max_hp: 9 },
      attacks: [],
      equipment: [],
      inventory: [],
      dull: false,
      natural_armor: [],
      ward: null,
      immune: [],
      vulnerable: [],
      xp: 0,
    };
    const { seen } = signedIn({
      bestiary_ids: [BESTIARY],
      monster_sheets: [ghoulSheet],
      npc_sheets: [{ ...MONK_SHEET, allied_monsters: [LICH] }],
    });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=npcs`);

    const list = within(await (await npcsPanel()).findByRole('list', { name: '인물 시트' }));
    expect(list.getByText('근력 8 · 민첩 10 · 건강 10 · HP 6 · 우호 · 상인 · 소지품 1 · 한편 몬스터 1')).toBeInTheDocument();
    await userEvent.click(list.getByRole('button', { name: '수도사 시트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    const allies = within(dialog.getByRole('group', { name: '한편인 몬스터' }));
    expect(await allies.findByRole('checkbox', { name: '구울' })).not.toBeChecked();
    expect(allies.getByRole('checkbox', { name: /리치\(시트 없음\)/ })).toBeChecked();

    await userEvent.click(allies.getByRole('checkbox', { name: '구울' }));
    await userEvent.click(allies.getByRole('checkbox', { name: /리치\(시트 없음\)/ }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.npc_sheets as NpcSheet[])[0]?.allied_monsters).toEqual([GHOUL]);
  });

  it('로어북의 인물이 아닌 것의 시트는 지울 수만 있다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=npcs`);

    const list = within(await (await npcsPanel()).findByRole('list', { name: '인물 시트' }));
    await userEvent.click(list.getByRole('button', { name: '(붙인 로어북의 인물이 아님) 시트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.queryByRole('button', { name: '저장' })).toBeNull();
    await userEvent.click(dialog.getByRole('button', { name: '시트 지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.npc_sheets as NpcSheet[]).map((npc) => npc.entry_id)).toEqual([MONK]);
  });
});

describe('인물 입력', () => {
  it('공격: 이름은 꼭, 겹치지 않게, 무기는 장비에 있는 물건', () => {
    const attack = { name: '물기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: '', cost: null, effects: [], nature: null, defense: '' };
    expect(attacksHints([{ ...attack, name: ' ' }], [])[0]).toContain('이름');
    expect(attacksHints([attack, attack], [])[1]).toBe('같은 이름의 공격이 위에 있습니다.');
    expect(attacksHints([{ ...attack, weapon: SWORD }], [])[0]).toBe('무기는 장비에 적은 물건이어야 합니다.');
    expect(attacksHints([{ ...attack, weapon: SWORD }], [SWORD])).toEqual({});
  });

  it('막는 능력치(#254)는 받은 그대로 두고, 비우면 룰북의 것(null)으로 보낸다', () => {
    const attack = { name: '독안개', ability: 'con', difficulty: 'normal', harm: 'light', weapon: null, cost: null, effects: [], defense: 'con' };
    const drafts = attackDrafts([attack, { ...attack, name: '칼', defense: null }]);
    expect(drafts.map((draft) => draft.defense)).toEqual(['con', '']);
    expect(toAttacks(drafts).map((one) => one.defense)).toEqual(['con', null]);
    expect(defaultDefense(RULES as unknown as Ruleset)).toBe('룰북의 것(민첩)');
    expect(defaultDefense({ ...RULES, defense: { ability: 'luck' } } as unknown as Ruleset)).toBe('룰북의 것(luck)');
    expect(defaultDefense({ ...RULES, defense: null } as unknown as Ruleset)).toBe('룰북의 것(맞서 굴리지 않음)');
  });

  it('공격의 비용(#805)은 고르는 칸이 없어도 저장할 때 그대로 간다', () => {
    const cost = { resource: 'mana', amount: 2 };
    const attack = { name: '화염구', ability: 'int', difficulty: 'normal', harm: 'light', weapon: null, cost, effects: [] };
    expect(toAttacks(attackDrafts([attack]))[0]?.cost).toEqual(cost);
  });

  it('효과만 있는 공격(#805)은 피해의 양을 비워도 되고, 효과는 그대로 간다', () => {
    const effects = [{ kind: 'injure' as const, injury: 'poisoned' }];
    const spit = { name: '독 뿜기', ability: 'str', difficulty: 'normal', harm: null, weapon: null, cost: null, effects };
    const drafts = attackDrafts([spit]);
    expect(attacksHints(drafts, [])).toEqual({});
    expect(toAttacks(drafts)[0]).toMatchObject({ harm: null, effects });
    expect(attacksHints([{ ...drafts[0]!, effects: [] }], [])[0]).toBe('능력치, 난이도, 피해의 양을 골라 주세요.');
  });

  it('빈 시트는 막고, 떨어질 확률은 1~100. 한 줄의 글', () => {
    const blank = npcDraft(undefined, rules);
    expect(hasNpcHints(npcHints(blank, rules, []))).toBe(true);
    const draft = { ...npcDraft(MONK_SHEET as unknown as NpcSheet, rules) };
    expect(hasNpcHints(npcHints(draft, rules, [SWORD_RULE as ItemRule]))).toBe(false);
    const zero = { ...draft, inventory: [{ entryId: BREAD, count: '1', wear: [], chance: '0' }] };
    expect(npcHints(zero, rules, []).inventory[0]).toBe('떨어질 확률은 1~100 사이의 정수입니다.');
    expect(npcLine({ ...(MONK_SHEET as unknown as NpcSheet), dull: true, merchant: false }, null)).toBe('str 8 · dex 10 · con 10 · HP 6 · 우호 · 둔함 · 소지품 1');
  });
});

describe('한편인 몬스터 고르기', () => {
  it('시트를 적은 몬스터의 차례이고, 고른 것 중 시트가 없는 것은 뒤에 남는다', () => {
    expect(allyChoices([GHOUL], [LICH, GHOUL])).toEqual([
      { id: GHOUL, sheeted: true },
      { id: LICH, sheeted: false },
    ]);
  });

  it('넣으면 끝에 붙고 두 번 넣지 않으며, 빼면 사라진다', () => {
    expect(withAlly([GHOUL], LICH, true)).toEqual([GHOUL, LICH]);
    expect(withAlly([GHOUL], GHOUL, true)).toEqual([GHOUL]);
    expect(withAlly([GHOUL, LICH], GHOUL, false)).toEqual([LICH]);
  });

  it('게시 점검의 npc_ally_missing 은 인물 탭으로 간다', () => {
    expect(problemLine('npc_ally_missing')).toEqual({ text: '인물의 한편인 몬스터 가운데 시트를 적지 않은 몬스터가 있습니다.', section: 'npcs' });
  });
});
