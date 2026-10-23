// web/apps/web/src/pages/trpg/studio/scenarios/Characters.test.tsx
// 시나리오의 캐릭터 탭(B9). 방식과 추천 인원, 기본 시트, 최대 HP 를 탭의 저장으로 보내기. 프리젠을 창에서 더하고 고치고 지우기
// (소지품과 돈은 그대로). 룰북이 없을 때. 입력의 순수한 함수(방식의 차례, 시트, 최대 HP, 보낼 칸, 프리젠의 이름).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { Ruleset, ScenarioDetail } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { charactersDraft, charactersHints, hpFormulaText, toCharactersBody, toggleMode } from './charactersForm';
import { pregenDraft, pregenHints, toPregen } from './pregenForm';
import { sheetDraft, sheetHints, toSheet } from './sheetForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const rules = RULES as unknown as Ruleset;

const KNIGHT = {
  name: '기사',
  description: '',
  sheet: { abilities: { str: 16, dex: 10, con: 14 }, max_hp: 14 },
  items: [{ entry_id: 'sword', count: 1, wear: ['main_hand'] }],
  money: 30,
};

function scenario(extra: Record<string, unknown> = {}) {
  return scenarioDetail({
    rulebook_id: RULEBOOK,
    openings: ['종이 울린다.'],
    pregens: [KNIGHT],
    ...extra,
  });
}

function rulebook() {
  return { id: RULEBOOK, title: '수도원 규칙', description: '', gm_guide: '', visibility: 'private', created_at: '', updated_at: '', rules: RULES };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenario(start);
  const installed = installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, rulebook()),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
  });
  return installed;
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body);
}

async function charactersPanel() {
  return within(await screen.findByRole('tabpanel', { name: '캐릭터' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캐릭터 탭', () => {
  it('방식과 인원, 기본 시트, 최대 HP 를 탭의 저장으로 보낸다. 시트를 반만 채우면 막는다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const panel = await charactersPanel();
    const form = within(await panel.findByRole('form', { name: '캐릭터' }));
    await userEvent.selectOptions(form.getByRole('combobox', { name: '최소' }), '2');
    await userEvent.click(form.getByRole('checkbox', { name: '능력치를 직접 적기' }));
    await userEvent.click(form.getByRole('checkbox', { name: '주사위로 굴린 점수 놓기' }));
    await userEvent.click(form.getByRole('checkbox', { name: '방장이 다시 굴리게 해 줄 수 있음' }));
    expect(form.getByText(/최대 HP = 기준값 \+ 건강의 보정/)).toBeInTheDocument();

    const sheet = within(form.getByRole('group', { name: /기본 시트/ }));
    await userEvent.type(sheet.getByRole('textbox', { name: '근력' }), '12');
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(sheet.getByRole('textbox', { name: '민첩' }), '12');
    await userEvent.type(sheet.getByRole('textbox', { name: '건강' }), '19');
    await userEvent.type(sheet.getByRole('textbox', { name: '최대 HP' }), '10');
    expect(sheet.getByText('3~18 사이의 정수입니다.')).toBeInTheDocument();
    await userEvent.clear(sheet.getByRole('textbox', { name: '건강' }));
    await userEvent.type(sheet.getByRole('textbox', { name: '건강' }), '12');
    await userEvent.type(form.getByRole('textbox', { name: '기준값' }), '8');
    await userEvent.type(form.getByRole('textbox', { name: '상한' }), '20');
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)[0]).toEqual({
      recommended_players: { min: 2, max: 4 },
      character_modes: ['pregen', 'custom', 'manual', 'rolled'],
      reroll_allowed: true,
      default_sheet: { abilities: { str: 12, dex: 12, con: 12 }, max_hp: 10 },
      player_made_hp: { base: 8, cap: 20 },
    });
  });

  it('프리젠을 창에서 더하고 고치면 목록을 통째로 보내고, 소지품과 돈은 그대로 둔다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const panel = await charactersPanel();
    const list = within(await panel.findByRole('list', { name: '프리젠' }));
    expect(list.getByText('근력 16 · 민첩 10 · 건강 14 · HP 14')).toBeInTheDocument();
    expect(list.getByText(/소지품 1줄 · 돈 30/)).toBeInTheDocument();

    await userEvent.click(panel.getByRole('button', { name: '프리젠 더하기' }));
    const adding = within(await screen.findByRole('dialog'));
    await userEvent.type(adding.getByRole('textbox', { name: '이름' }), '기사');
    expect(adding.getByText('같은 이름의 프리젠이 있습니다.')).toBeInTheDocument();
    await userEvent.clear(adding.getByRole('textbox', { name: '이름' }));
    await userEvent.type(adding.getByRole('textbox', { name: '이름' }), '사제');
    await userEvent.click(adding.getByRole('button', { name: '더하기' }));
    expect(await list.findByText('사제')).toBeInTheDocument();
    expect(patches(seen)[0]).toEqual({ pregens: [KNIGHT, { name: '사제', description: '', sheet: null, items: [], money: 0 }] });

    await userEvent.click(list.getByRole('button', { name: '기사 고치기' }));
    const editing = within(await screen.findByRole('dialog'));
    expect(editing.getByRole('textbox', { name: '근력' })).toHaveValue('16');
    await userEvent.clear(editing.getByRole('textbox', { name: '근력' }));
    await userEvent.type(editing.getByRole('textbox', { name: '근력' }), '17');
    await userEvent.click(editing.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1] as { pregens: unknown[] }).pregens[0]).toEqual({ ...KNIGHT, sheet: { abilities: { str: 17, dex: 10, con: 14 }, max_hp: 14 } });

    await userEvent.click(list.getByRole('button', { name: '사제 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(3));
    expect((patches(seen)[2] as { pregens: { name: string }[] }).pregens.map((pregen) => pregen.name)).toEqual(['기사']);
  });

  it('룰북이 없으면 재료 탭으로 안내하고, 시트를 보내지 않는다', async () => {
    const { seen } = signedIn({ rulebook_id: null });
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const panel = await charactersPanel();
    expect(await panel.findByText(/룰북을 고르기 전에는 시트를 적을 수 없습니다/)).toBeInTheDocument();
    const form = within(panel.getByRole('form', { name: '캐릭터' }));
    expect(form.queryByRole('group', { name: /기본 시트/ })).toBeNull();
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]).not.toHaveProperty('default_sheet');

    await userEvent.click(panel.getByRole('button', { name: '재료 탭으로' }));
    expect(screen.getByRole('tab', { name: '재료' })).toHaveAttribute('aria-selected', 'true');
  });
});

describe('캐릭터 입력', () => {
  it('방식은 차례를 지키고, 하나는 있어야 하고, 최소가 최대보다 크면 알린다', () => {
    expect(toggleMode(['rolled'], 'pregen')).toEqual(['pregen', 'rolled']);
    const draft = charactersDraft(scenario() as unknown as ScenarioDetail, rules);
    expect(charactersHints({ ...draft, modes: [] }, rules).character_modes).toBeDefined();
    expect(charactersHints({ ...draft, minPlayers: 3, maxPlayers: 2 }, rules).recommended_players).toBe('최소 인원이 최대 인원보다 큽니다.');
    expect(charactersHints({ ...draft, modes: ['manual'], hpBase: '20', hpCap: '10' }, rules).hp_cap).toBe('상한이 기준값보다 작습니다.');
  });

  it('쓰지 않는 방식의 값은 보내지 않는다. 비운 최대 HP 와 시트는 null', () => {
    const draft = charactersDraft(scenario() as unknown as ScenarioDetail, rules);
    expect(toCharactersBody({ ...draft, modes: ['pregen'], reroll: true }, rules)).toEqual({
      recommended_players: { min: 1, max: 4 },
      character_modes: ['pregen'],
      reroll_allowed: false,
    });
    expect(toCharactersBody({ ...draft, modes: ['custom', 'manual'] }, rules)).toMatchObject({ default_sheet: null, player_made_hp: null });
    expect(toCharactersBody({ ...draft, modes: ['custom'] }, null)).not.toHaveProperty('default_sheet');
  });

  it('시트: 다 비우면 없음, 반만 채우면 알림, 룰북에 없는 능력치는 빠진다', () => {
    const blank = sheetDraft(null, rules);
    expect(sheetHints(blank, rules)).toEqual({});
    expect(toSheet(blank, rules)).toBeNull();
    expect(Object.keys(sheetHints({ ...blank, maxHp: '10' }, rules))).toEqual(['str', 'dex', 'con']);
    const old = sheetDraft({ abilities: { str: 10, dex: 10, con: 10, luck: 5 }, max_hp: 8 }, rules);
    expect(toSheet(old, rules)).toEqual({ abilities: { str: 10, dex: 10, con: 10 }, max_hp: 8 });
  });

  it('프리젠: 대소문자만 다른 이름도 겹침, 룰북이 없으면 원래 시트를 둔다. 최대 HP 의 식', () => {
    expect(pregenHints({ name: 'Knight', description: '', sheet: null }, null, ['knight']).name).toBe('같은 이름의 프리젠이 있습니다.');
    const draft = pregenDraft(KNIGHT as never, null);
    expect(toPregen({ ...draft, name: ' 기사 ' }, null, KNIGHT as never)).toEqual(KNIGHT);
    expect(hpFormulaText({ ...rules, hp_ability: null })).toContain('기준값이 그대로 최대 HP');
  });
});
