// web/apps/web/src/pages/trpg/studio/scenarios/Npcs.test.tsx
// 시나리오의 인물 탭(B9). 기본 인물 시트를 탭의 저장으로, 인물 시트(태도, 상인, 장비와 착용·떨어질 확률, 소지품, 공격과 무기)를
// 창에서 바로 보내기, 시트 지우기, 로어북의 인물이 아닌 것의 시트. 입력의 순수한 함수(장비·소지품의 겹침, 공격, 빈 시트).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { ItemRule, NpcSheet, Ruleset } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { attacksHints } from './attacksForm';
import { hasNpcHints, npcDraft, npcHints, npcLine } from './npcForm';

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
const rules = RULES as unknown as Ruleset;

const SWORD_RULE = { entry_id: SWORD, kind: 'gear', rarity: 'normal', effects: [], price: 10, slots: ['main_hand'], slot_count: 1, attack: 2, ap: null, defense: null, guard: null, ward: null, aids: [] };

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

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenario(start);
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [entry(GUARD, '늙은 문지기', 'person'), entry(MONK, '수도사', 'person'), entry(SWORD, '녹슨 검', 'item'), entry(BREAD, '검은 빵', 'item')]),
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
      attacks: [{ name: '검 휘두르기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: SWORD }],
    });
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
    const attack = { name: '물기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: '' };
    expect(attacksHints([{ ...attack, name: ' ' }], [])[0]).toContain('이름');
    expect(attacksHints([attack, attack], [])[1]).toBe('같은 이름의 공격이 위에 있습니다.');
    expect(attacksHints([{ ...attack, weapon: SWORD }], [])[0]).toBe('무기는 장비에 적은 물건이어야 합니다.');
    expect(attacksHints([{ ...attack, weapon: SWORD }], [SWORD])).toEqual({});
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
