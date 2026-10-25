// web/apps/web/src/pages/trpg/studio/scenarios/Wanders.test.tsx
// 무작위 조우 표(B9 몬스터 탭, #283). 표 더하기(장소, 때, 확률, 몬스터 줄의 마리 수·몫·기습)를 창에서 바로 보내기,
// 같은 장소의 겹치는 때 막기, 확률 0 이면 몬스터를 보내지 않기(안전한 곳), 지우기. 입력의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { WanderTable } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { timesOverlap, toggleTime, toWander, wanderDraft, wanderHints, wanderLine, weightShare } from './wandersForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const BESTIARY = '00000000-0000-4000-8000-0000000000d4';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const VILLAGE = '00000000-0000-4000-8000-00000000c005';
const GHOUL = '00000000-0000-4000-8000-00000000e001';
const RAT = '00000000-0000-4000-8000-00000000e003';

const SHEET = { sheet: { abilities: { str: 14, dex: 10, con: 12 }, max_hp: 9 }, attacks: [], equipment: [], inventory: [], dull: false, natural_armor: [], ward: null, immune: [], vulnerable: [] };
const NIGHT_CRYPT = { place_id: CRYPT, times: ['night'], chance: 30, monsters: [{ monster_id: GHOUL, count: 2, weight: 1, surprise: 'none' }] };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function monster(id: string, name: string) {
  return { id, name, kind: 'beast', content: '', unique: false, created_at: '', updated_at: '' };
}

function signedIn() {
  let current = scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    bestiary_ids: [BESTIARY],
    start_place: VILLAGE,
    landmarks: [CRYPT],
    monster_sheets: [
      { ...SHEET, monster_id: GHOUL },
      { ...SHEET, monster_id: RAT },
    ],
    wanders: [NIGHT_CRYPT],
  });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () => json(200, [entry(CRYPT, '지하 묘지', 'place'), entry(VILLAGE, '마을', 'place')]),
    [`GET ${GAME}/bestiaries/${BESTIARY}/monsters`]: () => json(200, [monster(GHOUL, '구울'), monster(RAT, '시궁쥐')]),
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

async function wandersList() {
  const panel = within(await screen.findByRole('tabpanel', { name: '몬스터' }));
  return { panel, list: within(await panel.findByRole('list', { name: '무작위 조우 표' })) };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('무작위 조우 표', () => {
  it('같은 장소의 겹치는 때는 막고, 장소·때·확률·몬스터 줄(마리 수, 몫, 기습)을 창에서 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=monsters`);

    const { panel, list } = await wandersList();
    expect(list.getByText('지하 묘지 · 밤 · 30% · 구울 ×2(100%)')).toBeInTheDocument();
    await userEvent.click(panel.getByRole('button', { name: '표 더하기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '장소' }), CRYPT);
    expect(dialog.getByText('이 장소에 같은 때를 쓰는 표가 이미 있습니다. 때를 나눠 주세요.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('checkbox', { name: '새벽' }));
    await userEvent.click(dialog.getByRole('checkbox', { name: '낮' }));
    expect(dialog.getByText('조우가 날 확률이 있으면 나올 몬스터를 하나는 적어 주세요.')).toBeInTheDocument();

    await userEvent.click(dialog.getByRole('button', { name: '몬스터 더하기' }));
    await userEvent.click(dialog.getByRole('button', { name: '몬스터 더하기' }));
    const first = within(dialog.getByRole('group', { name: '몬스터 1' }));
    await userEvent.selectOptions(first.getByRole('combobox', { name: '몬스터' }), RAT);
    await userEvent.clear(first.getByRole('textbox', { name: '마리 수(1~10)' }));
    await userEvent.type(first.getByRole('textbox', { name: '마리 수(1~10)' }), '4');
    await userEvent.clear(first.getByRole('textbox', { name: '몫(1~100)' }));
    await userEvent.type(first.getByRole('textbox', { name: '몫(1~100)' }), '3');
    const second = within(dialog.getByRole('group', { name: '몬스터 2' }));
    await userEvent.selectOptions(second.getByRole('combobox', { name: '몬스터' }), RAT);
    expect(second.getByText(/같은 몬스터가 두 줄입니다/)).toBeInTheDocument();
    await userEvent.selectOptions(second.getByRole('combobox', { name: '몬스터' }), GHOUL);
    await userEvent.selectOptions(second.getByRole('combobox', { name: '기습' }), 'monsters');
    expect(first.getByText('뽑힐 비율: 75%')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.wanders as WanderTable[])[1]).toEqual({
      place_id: CRYPT,
      times: ['dawn', 'day'],
      chance: 10,
      monsters: [
        { monster_id: RAT, count: 4, weight: 3, surprise: 'none' },
        { monster_id: GHOUL, count: 1, weight: 1, surprise: 'monsters' },
      ],
    });
    expect(await list.findByText('지하 묘지 · 새벽, 낮 · 10% · 시궁쥐 ×4(75%), 구울(25%, 몬스터가 매복)')).toBeInTheDocument();
  });

  it('확률 0 은 안전한 곳이라 몬스터를 적지 않는다. 장소를 비우면 기본 표다. 지울 수 있다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=monsters`);

    const { panel, list } = await wandersList();
    await userEvent.click(panel.getByRole('button', { name: '표 더하기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '장소' }), VILLAGE);
    await userEvent.clear(dialog.getByRole('textbox', { name: '조우가 날 확률(%, 0~100)' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '조우가 날 확률(%, 0~100)' }), '0');
    expect(dialog.queryByRole('button', { name: '몬스터 더하기' })).toBeNull();
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.wanders as WanderTable[])[1]).toEqual({ place_id: VILLAGE, times: [], chance: 0, monsters: [] });
    expect(await list.findByText('마을 · 언제나 · 안전(조우 없음)')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '지하 묘지 밤 표 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect(patches(seen)[1]?.wanders).toEqual([{ place_id: VILLAGE, times: [], chance: 0, monsters: [] }]);
  });
});

describe('무작위 조우 표의 입력', () => {
  it('때: 차례를 지키고, 비운 때는 무엇과도 겹친다. 기본 표끼리도 겹침을 본다. 몫의 비율', () => {
    expect(toggleTime(['night'], 'dawn')).toEqual(['dawn', 'night']);
    expect(timesOverlap([], ['day'])).toBe(true);
    expect(timesOverlap(['dawn'], ['night'])).toBe(false);
    const tables = [{ place_id: null, times: [], chance: 5, monsters: [] }] as unknown as WanderTable[];
    expect(wanderHints({ ...wanderDraft(null), chance: '0' }, tables, null, []).fields.times).toContain('기본 표');
    expect(wanderHints({ ...wanderDraft(null), chance: '0' }, tables, 0, []).fields).toEqual({});
    expect(wanderHints({ ...wanderDraft(null), chance: '101' }, [], null, []).fields.chance).toBeDefined();
    expect(weightShare(1, 3)).toBe('33%');
    expect(weightShare(1, 0)).toBe('');
  });

  it('보낼 표: 기본 표는 place_id null, 확률 0 이면 몬스터를 비운다. 한 줄의 글', () => {
    const draft = { place: '', times: [], chance: '0', monsters: [{ monster: GHOUL, count: '1', weight: '1', surprise: 'none' as const }] };
    expect(toWander(draft)).toEqual({ place_id: null, times: [], chance: 0, monsters: [] });
    const name = (id: string) => (id === GHOUL ? '구울' : '?');
    expect(wanderLine({ place_id: null, times: ['evening', 'night'], chance: 15, monsters: [{ monster_id: GHOUL, count: 1, weight: 2, surprise: 'none' }] } as WanderTable, name, name)).toBe(
      '기본 표 · 저녁, 밤 · 15% · 구울(100%)',
    );
  });
});
