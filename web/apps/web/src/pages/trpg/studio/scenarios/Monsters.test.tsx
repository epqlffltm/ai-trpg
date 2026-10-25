// web/apps/web/src/pages/trpg/studio/scenarios/Monsters.test.tsx
// 시나리오의 몬스터 탭(B9). 몬스터 시트(숫자, 타고난 방어, 불굴, 장비, 공격)를 창에서 바로 보내기와 시트 지우기,
// 조우 더하기(시트 있는 몬스터만, 네임드는 한 마리, 같은 장소의 같은 몬스터는 한 줄)와 지우기. 입력의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Encounter, MonsterSheet, Ruleset } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { encounterDraft, encounterHints, encounterLine } from './encountersForm';
import { hasMonsterHints, monsterDraft, monsterHints, monsterLine, toggledNature, toMonsterSheet } from './monsterForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const BESTIARY = '00000000-0000-4000-8000-0000000000d4';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const HALL = '00000000-0000-4000-8000-00000000c004';
const GHOUL = '00000000-0000-4000-8000-00000000e001';
const LICH = '00000000-0000-4000-8000-00000000e002';
const RAT = '00000000-0000-4000-8000-00000000e003';
const CLAW = '00000000-0000-4000-8000-00000000a020';
const rules = RULES as unknown as Ruleset;

const GHOUL_SHEET = {
  monster_id: GHOUL,
  sheet: { abilities: { str: 14, dex: 10, con: 12 }, max_hp: 9 },
  attacks: [{ name: '할퀴기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: null }],
  equipment: [],
  inventory: [],
  dull: false,
  natural_armor: [],
  ward: null,
  immune: ['poison'],
  vulnerable: [],
};
const LICH_SHEET = { ...GHOUL_SHEET, monster_id: LICH, attacks: [] };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function monster(id: string, name: string, unique = false) {
  return { id, name, kind: 'undead', content: '', unique, created_at: '', updated_at: '' };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    bestiary_ids: [BESTIARY],
    start_place: CRYPT,
    landmarks: [HALL],
    monster_sheets: [GHOUL_SHEET, LICH_SHEET],
    encounters: [{ place_id: CRYPT, monster_id: LICH, count: 1, surprise: 'none' }],
    ...start,
  });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () => json(200, [entry(CRYPT, '지하 묘지', 'place'), entry(HALL, '회랑', 'place'), entry(CLAW, '뼈 갈퀴', 'item')]),
    [`GET ${GAME}/bestiaries/${BESTIARY}/monsters`]: () => json(200, [monster(GHOUL, '구울'), monster(LICH, '리치', true), monster(RAT, '시궁쥐')]),
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

async function monstersPanel() {
  return within(await screen.findByRole('tabpanel', { name: '몬스터' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('몬스터 탭', () => {
  it('몬스터 시트를 창에서 적으면 목록을 통째로 보낸다. 타고난 방어와 불굴, 장비의 무기', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=monsters`);

    const list = within(await (await monstersPanel()).findByRole('list', { name: '몬스터 시트' }));
    expect(list.getByText('시트 없음(이 시나리오에 나오지 않음)')).toBeInTheDocument();
    expect(list.getByText('네임드')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '시궁쥐 시트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    for (const [name, value] of [['근력', '4'], ['민첩', '16'], ['건강', '6'], ['최대 HP', '3']]) {
      await userEvent.type(dialog.getByRole('textbox', { name }), value as string);
    }
    await userEvent.type(dialog.getByRole('textbox', { name: '주손' }), '11');
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.clear(dialog.getByRole('textbox', { name: '주손' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '주손' }), '1');
    await userEvent.type(dialog.getByRole('textbox', { name: '불굴 세이브' }), '4');
    await userEvent.click(dialog.getByRole('checkbox', { name: '정신에 면역' }));
    await userEvent.click(dialog.getByRole('checkbox', { name: '정신에 약함' }));
    expect(dialog.getByText('정신은(는) 면역과 약함에 함께 둘 수 없습니다.')).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(dialog.getByRole('checkbox', { name: '정신에 약함' }));
    await userEvent.click(dialog.getByRole('checkbox', { name: '독에 약함' }));
    await userEvent.click(dialog.getByRole('button', { name: '장비 더하기' }));
    await userEvent.click(dialog.getByRole('button', { name: '공격 더하기' }));
    const attack = within(dialog.getByRole('group', { name: '공격 1' }));
    await userEvent.type(attack.getByRole('textbox', { name: '이름' }), '물기');
    await userEvent.selectOptions(attack.getByRole('combobox', { name: '무기' }), CLAW);
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const sent = patches(seen)[0]?.monster_sheets as MonsterSheet[];
    expect(sent.map((one) => one.monster_id)).toEqual([GHOUL, LICH, RAT]);
    expect(sent[2]).toEqual({
      monster_id: RAT,
      sheet: { abilities: { str: 4, dex: 16, con: 6 }, max_hp: 3 },
      dull: false,
      natural_armor: [{ slot: 'main_hand', defense: 1 }],
      ward: 4,
      equipment: [{ entry_id: CLAW, count: 1, chance: 100, wear: [] }],
      inventory: [],
      attacks: [{ name: '물기', ability: 'str', difficulty: 'normal', harm: 'light', weapon: CLAW }],
      immune: ['mind'],
      vulnerable: ['poison'],
    });
    // 고치지 않은 시트의 면역은 그대로 간다
    expect(sent[0]?.immune).toEqual(['poison']);
  });

  it('조우는 시트 있는 몬스터만, 네임드는 한 마리. 더하고 지운다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=monsters`);

    const panel = await monstersPanel();
    const encounters = within(await panel.findByRole('list', { name: '조우' }));
    expect(encounters.getByText('지하 묘지 · 리치 ×1')).toBeInTheDocument();

    await userEvent.click(panel.getByRole('button', { name: '조우 더하기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.queryByRole('option', { name: '시궁쥐' })).toBeNull();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '장소' }), HALL);
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '몬스터' }), LICH);
    expect(dialog.getByText('네임드 몬스터는 판 전체에 한 마리입니다. 다른 장소에 이미 있습니다.')).toBeInTheDocument();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '몬스터' }), GHOUL);
    await userEvent.clear(dialog.getByRole('textbox', { name: '마리 수(1~10)' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '마리 수(1~10)' }), '3');
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '기습' }), 'monsters');
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.encounters as Encounter[])[1]).toEqual({ place_id: HALL, monster_id: GHOUL, count: 3, surprise: 'monsters' });
    expect(await encounters.findByText('회랑 · 구울 ×3 · 몬스터가 매복')).toBeInTheDocument();

    await userEvent.click(encounters.getByRole('button', { name: '지하 묘지의 리치 조우 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1]?.encounters as Encounter[]).map((one) => one.monster_id)).toEqual([GHOUL]);
  });

  it('시트를 지우면 그 몬스터는 판에서 빠진다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=monsters`);

    const list = within(await (await monstersPanel()).findByRole('list', { name: '몬스터 시트' }));
    await userEvent.click(list.getByRole('button', { name: '리치 시트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('조우에 놓인 몬스터입니다. 시트를 지우면 그 조우가 게시 점검에 걸립니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '시트 지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.monster_sheets as MonsterSheet[]).map((one) => one.monster_id)).toEqual([GHOUL]);
  });
});

describe('몬스터 입력', () => {
  it('빈 시트는 막고, 빈 방어 칸은 보내지 않는다', () => {
    expect(hasMonsterHints(monsterHints(monsterDraft(undefined, rules), rules, []))).toBe(true);
    const draft = monsterDraft(GHOUL_SHEET as unknown as MonsterSheet, rules);
    expect(hasMonsterHints(monsterHints(draft, rules, []))).toBe(false);
    expect(toMonsterSheet(GHOUL, { ...draft, natural: { main_hand: '', off_hand: '2' } }, rules).natural_armor).toEqual([{ slot: 'off_hand', defense: 2 }]);
  });

  it('면역과 약함은 고친 시트에도 남고, 성질표의 차례로 보낸다', () => {
    const draft = monsterDraft(GHOUL_SHEET as unknown as MonsterSheet, rules);
    expect(toMonsterSheet(GHOUL, draft, rules).immune).toEqual(['poison']);
    expect(toggledNature(['mind'], 'poison', true)).toEqual(['poison', 'mind']);
    expect(toggledNature(['poison', 'mind'], 'poison', false)).toEqual(['mind']);
    expect(monsterHints({ ...draft, vulnerable: ['poison'] }, rules, []).natures).toBe('독은(는) 면역과 약함에 함께 둘 수 없습니다.');
    expect(monsterLine({ ...GHOUL_SHEET, vulnerable: ['mind'] } as unknown as MonsterSheet, rules)).toContain('면역 독 · 약함 정신');
  });

  it('조우: 같은 장소의 같은 몬스터, 네임드 두 마리, 마리 수', () => {
    const existing = [{ place_id: CRYPT, monster_id: GHOUL, count: 2, surprise: 'none' }] as Encounter[];
    const choices = [
      { id: GHOUL, name: '구울', unique: false },
      { id: LICH, name: '리치', unique: true },
    ];
    expect(encounterHints({ ...encounterDraft(null), place: CRYPT, monster: GHOUL }, existing, null, choices).monster).toContain('이미 있습니다');
    expect(encounterHints({ ...encounterDraft(null), place: HALL, monster: LICH, count: '2' }, existing, null, choices).count).toContain('한 마리');
    expect(encounterHints({ ...encounterDraft(null), place: HALL, monster: GHOUL, count: '11' }, existing, null, choices).count).toBeDefined();
    expect(encounterLine(existing[0] as Encounter, () => '묘지', () => '구울')).toBe('묘지 · 구울 ×2');
  });
});
