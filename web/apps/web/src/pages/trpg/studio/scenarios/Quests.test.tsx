// web/apps/web/src/pages/trpg/studio/scenarios/Quests.test.tsx
// 시나리오의 퀘스트·사건 탭(B9). 퀘스트(처음 상태, 이루는 조건과 배달, 드러나는 조건의 퀘스트 잇기, 실패하는 조건, 보상, 기한)와
// 사건(일어나는 조건, 캐릭터 옮기기, 길의 문 잠그기)을 창에서 바로 보내기. 입력의 순수한 함수(조건, 효과, 한 줄).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { HappeningRule, QuestRule } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { conditionLine, conditionsHints, toConditions, type Targets } from './conditionsForm';
import { happeningDraft, happeningHints, happeningLine, toHappening } from './happeningForm';
import { questDraft, toQuestRule } from './questForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const BESTIARY = '00000000-0000-4000-8000-0000000000d4';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GATE = '00000000-0000-4000-8000-00000000c001';
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const RELIC = '00000000-0000-4000-8000-00000000a030';
const KEEPER = '00000000-0000-4000-8000-00000000b001';
const GHOUL = '00000000-0000-4000-8000-00000000e001';
const HUNT = '00000000-0000-4000-8000-00000000f001';
const DELIVER = '00000000-0000-4000-8000-00000000f002';
const COLLAPSE = '00000000-0000-4000-8000-00000000f003';

const GHOUL_SHEET = {
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
};
const DOOR = { from_place: GATE, to_place: CRYPT, two_way: true, visibility: 'open', find: null, travel_minutes: null, cross: null, lock: null, bar: { side: GATE, barred: false }, force: null };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    bestiary_ids: [BESTIARY],
    start_place: GATE,
    routes: [DOOR],
    monster_sheets: [GHOUL_SHEET],
    quests: [{ entry_id: HUNT, start: 'active', reward: [], reward_money: 0, time_limit_minutes: null, conditions: [{ kind: 'defeat_monster', target: GHOUL, count: 3, consume: false }], match: 'all', reveal: [], reveal_match: 'all', fail: [], fail_match: 'all' }],
    ...start,
  });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [
        entry(GATE, '수도원 문', 'place'),
        entry(CRYPT, '지하 묘지', 'place'),
        entry(RELIC, '성유물', 'item'),
        entry(KEEPER, '늙은 문지기', 'person'),
        entry(HUNT, '구울 사냥', 'event'),
        entry(DELIVER, '성유물 배달', 'event'),
        entry(COLLAPSE, '묘지 붕괴', 'event'),
      ]),
    [`GET ${GAME}/bestiaries/${BESTIARY}/monsters`]: () => json(200, [{ id: GHOUL, name: '구울', kind: 'undead', content: '', unique: false, created_at: '', updated_at: '' }]),
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

async function questsPanel() {
  return within(await screen.findByRole('tabpanel', { name: '퀘스트·사건' }));
}

const TARGETS: Targets = {
  places: [{ id: GATE, name: '수도원 문' }],
  monsters: [{ id: GHOUL, name: '구울' }],
  items: [{ id: RELIC, name: '성유물' }],
  npcs: [{ id: KEEPER, name: '늙은 문지기' }],
  quests: [{ id: HUNT, name: '구울 사냥' }],
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('퀘스트·사건 탭', () => {
  it('퀘스트: 배달(가져감), 앞 퀘스트의 성공으로 드러남, 인물이 죽으면 실패, 보상과 기한을 창에서 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=quests`);

    const list = within(await (await questsPanel()).findByRole('list', { name: '퀘스트' }));
    expect(list.getByText('진행 중으로 시작 · 이룸: 구울 3마리를 쓰러뜨린다')).toBeInTheDocument();
    expect(list.getAllByText('규칙 없음(숨김으로 시작, 조건 없음)')).toHaveLength(2);

    await userEvent.click(list.getByRole('button', { name: '성유물 배달 퀘스트 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '이루는 조건 더하기' }));
    const goal = within(dialog.getByRole('group', { name: '이루는 조건 1' }));
    await userEvent.selectOptions(goal.getByRole('combobox', { name: '종류' }), 'hold_item');
    await userEvent.selectOptions(goal.getByRole('combobox', { name: '대상' }), RELIC);
    await userEvent.click(goal.getByRole('checkbox', { name: '이룰 때 그 물건을 가져간다(배달)' }));

    await userEvent.click(dialog.getByRole('button', { name: '드러나는 조건 더하기' }));
    const reveal = within(dialog.getByRole('group', { name: '드러나는 조건 1' }));
    await userEvent.selectOptions(reveal.getByRole('combobox', { name: '종류' }), 'quest_succeeded');
    expect(reveal.queryByRole('option', { name: '성유물 배달' })).toBeNull();
    await userEvent.selectOptions(reveal.getByRole('combobox', { name: '대상' }), HUNT);

    await userEvent.click(dialog.getByRole('button', { name: '실패하는 조건 더하기' }));
    const fail = within(dialog.getByRole('group', { name: '실패하는 조건 1' }));
    await userEvent.selectOptions(fail.getByRole('combobox', { name: '종류' }), 'npc_dead');
    await userEvent.selectOptions(fail.getByRole('combobox', { name: '대상' }), KEEPER);

    await userEvent.clear(dialog.getByRole('textbox', { name: '살아 있는 캐릭터마다 받는 돈' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '살아 있는 캐릭터마다 받는 돈' }), '30');
    await userEvent.type(dialog.getByRole('textbox', { name: '기한(분, 선택)' }), '1440');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const sent = patches(seen)[0]?.quests as QuestRule[];
    expect(sent[1]).toEqual({
      entry_id: DELIVER,
      start: 'hidden',
      conditions: [{ kind: 'hold_item', target: RELIC, count: 1, consume: true }],
      match: 'all',
      reveal: [{ kind: 'quest_succeeded', target: HUNT, count: 1, consume: false }],
      reveal_match: 'all',
      fail: [{ kind: 'npc_dead', target: KEEPER, count: 1, consume: false }],
      fail_match: 'all',
      reward: [],
      reward_money: 30,
      time_limit_minutes: 1440,
    });
  });

  it('사건: 조건이 채워지면 모두 옮기고 문의 빗장을 잠그는 규칙을 창에서 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=quests`);

    const list = within(await (await questsPanel()).findByRole('list', { name: '사건' }));
    await userEvent.click(list.getByRole('button', { name: '묘지 붕괴 사건 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByText('일어나는 조건을 하나는 적어 주세요.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '일어나는 조건 더하기' }));
    await userEvent.selectOptions(within(dialog.getByRole('group', { name: '일어나는 조건 1' })).getByRole('combobox', { name: '대상' }), CRYPT);

    await userEvent.click(dialog.getByRole('button', { name: '효과 더하기' }));
    await userEvent.selectOptions(within(dialog.getByRole('group', { name: '효과 1' })).getByRole('combobox', { name: '옮겨 갈 장소' }), GATE);
    await userEvent.click(dialog.getByRole('button', { name: '효과 더하기' }));
    const second = within(dialog.getByRole('group', { name: '효과 2' }));
    await userEvent.selectOptions(second.getByRole('combobox', { name: '종류' }), 'lock_route');
    await userEvent.selectOptions(second.getByRole('combobox', { name: '길' }), `${GATE}|${CRYPT}`);
    await userEvent.selectOptions(second.getByRole('combobox', { name: '장치' }), 'bar');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.happenings as HappeningRule[])[0]).toEqual({
      entry_id: COLLAPSE,
      when: [{ kind: 'reach_place', target: CRYPT, count: 1, consume: false }],
      match: 'all',
      effects: [
        { kind: 'move', to_place: GATE, from_place: null },
        { kind: 'lock_route', from_place: GATE, to_place: CRYPT, device: 'bar' },
      ],
    });
    expect(await list.findByText('지하 묘지에 닿는다 ⇒ 모두 → 수도원 문, 수도원 문–지하 묘지의 빗장 잠금')).toBeInTheDocument();
  });
});

describe('퀘스트·사건 입력', () => {
  it('조건: 대상, 자기 자신, 같은 조건, 개수. 세지 않는 조건은 1, 가져가기는 물건 지니기만', () => {
    expect(conditionsHints([{ kind: 'reach_place', target: '', count: '1', consume: false }], HUNT)[0]).toBe('대상을 골라 주세요.');
    expect(conditionsHints([{ kind: 'quest_failed', target: HUNT, count: '1', consume: false }], HUNT)[0]).toBe('자기 자신을 가리킬 수 없습니다.');
    const ghoul = { kind: 'defeat_monster' as const, target: GHOUL, count: '100', consume: true };
    expect(conditionsHints([ghoul], HUNT)[0]).toContain('개수');
    expect(toConditions([{ ...ghoul, count: '2' }, { kind: 'reach_place', target: GATE, count: '5', consume: true }], true)).toEqual([
      { kind: 'defeat_monster', target: GHOUL, count: 2, consume: false },
      { kind: 'reach_place', target: GATE, count: 1, consume: false },
    ]);
    expect(conditionLine({ kind: 'lose_item', target: RELIC, count: 1, consume: false }, TARGETS)).toBe('지닌 성유물 1개 미만');
  });

  it('진행 중으로 시작하면 드러나는 조건을 보내지 않는다. 사건은 효과가 있어야 하고 옮기는 곳이 같으면 막는다', () => {
    const draft = { ...questDraft(undefined), start: 'active' as const, reveal: [{ kind: 'reach_place' as const, target: GATE, count: '1', consume: false }] };
    expect(toQuestRule(HUNT, draft).reveal).toEqual([]);
    const happening = happeningDraft(undefined);
    expect(happeningHints(happening, COLLAPSE).fields.effects).toBeDefined();
    const same = { ...happening, effects: [{ kind: 'move' as const, toPlace: GATE, fromPlace: GATE, npc: '', route: '', device: '' as const }] };
    expect(happeningHints(same, COLLAPSE).effects[0]).toContain('같습니다');
    const rule = toHappening(COLLAPSE, { ...same, when: [{ kind: 'npc_dead', target: KEEPER, count: '1', consume: false }], effects: [{ ...same.effects[0]!, fromPlace: '' }] });
    expect(happeningLine(rule as unknown as HappeningRule, TARGETS)).toBe('늙은 문지기 죽음 ⇒ 모두 → 수도원 문');
  });
});
