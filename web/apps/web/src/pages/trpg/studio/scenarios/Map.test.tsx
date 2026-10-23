// web/apps/web/src/pages/trpg/studio/scenarios/Map.test.tsx
// 시나리오의 지도 탭(B9). 시작 장소를 탭의 저장으로, 장소(명소, 커버, 인물의 자리)와 길을 창에서 바로 보내기.
// 다른 장소의 인물을 옮기기, 숨긴 길의 찾는 판정, 같은 두 장소의 길 막기, 길의 문을 그대로 두기, 길 지우기. 입력의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { RouteRule, ScenarioDetail } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { applyPlace, mapPlaces, placeLine } from './placesForm';
import { routeDraft, routeHints, toRoute } from './routesForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GATE = '00000000-0000-4000-8000-00000000c001';
const TOWER = '00000000-0000-4000-8000-00000000c002';
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const KEEPER = '00000000-0000-4000-8000-00000000b001';
const KEY = '00000000-0000-4000-8000-00000000a009';

const GATE_TOWER = {
  from_place: GATE,
  to_place: TOWER,
  two_way: true,
  visibility: 'open',
  find: null,
  travel_minutes: 30,
  cross: null,
  lock: { key: KEY, locked: true, pick: null },
  bar: null,
  force: null,
};

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function scenario(extra: Record<string, unknown> = {}) {
  return scenarioDetail({
    rulebook_id: RULEBOOK,
    lorebook_ids: [LOREBOOK],
    start_place: GATE,
    routes: [GATE_TOWER],
    npc_places: [{ entry_id: KEEPER, place_id: GATE }],
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
      json(200, [entry(GATE, '수도원 문', 'place'), entry(TOWER, '종탑', 'place'), entry(CRYPT, '지하 묘지', 'place'), entry(KEEPER, '늙은 문지기', 'person')]),
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

async function mapPanel() {
  return within(await screen.findByRole('tabpanel', { name: '지도' }));
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('지도 탭', () => {
  it('시작 장소를 탭의 저장으로 보낸다. 비우면 null', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const form = within(await (await mapPanel()).findByRole('form', { name: '지도' }));
    await userEvent.selectOptions(form.getByRole('combobox', { name: '시작 장소' }), '');
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    expect(await form.findByText('저장했습니다.')).toBeInTheDocument();
    expect(patches(seen)[0]).toEqual({ start_place: null });
  });

  it('장소의 창에서 명소, 커버, 인물을 고치면 셋을 함께 보낸다. 다른 장소의 인물은 옮긴다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const list = within(await (await mapPanel()).findByRole('list', { name: '장소' }));
    expect(list.getByText('시작 · 길 1 · 인물 1')).toBeInTheDocument();
    expect(list.getByText('맵 밖')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '지하 묘지 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('checkbox', { name: '명소로 둔다' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '커버(선택, 1~10)' }), '11');
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.clear(dialog.getByRole('textbox', { name: '커버(선택, 1~10)' }));
    await userEvent.type(dialog.getByRole('textbox', { name: '커버(선택, 1~10)' }), '5');
    expect(dialog.getByText('지금 수도원 문에 있습니다. 고르면 이곳으로 옮깁니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('checkbox', { name: /늙은 문지기/ }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]).toEqual({
      landmarks: [CRYPT],
      covers: [{ place_id: CRYPT, cover: 5 }],
      npc_places: [{ entry_id: KEEPER, place_id: CRYPT }],
      place_items: [],
    });
    expect(await list.findByText('명소 · 커버 5 · 인물 1')).toBeInTheDocument();
  });

  it('숨긴 길은 찾는 판정과 함께 더하고, 같은 두 장소의 길은 막는다. 고쳐도 길의 문은 그대로 두고, 지울 수 있다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const panel = await mapPanel();
    const routes = within(await panel.findByRole('list', { name: '길' }));
    expect(routes.getByText('수도원 문 ↔ 종탑 · 처음부터 앎 · 30분 · 자물쇠(잠김)')).toBeInTheDocument();

    await userEvent.click(panel.getByRole('button', { name: '길 더하기' }));
    const adding = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(adding.getByRole('combobox', { name: '한쪽 끝' }), TOWER);
    await userEvent.selectOptions(adding.getByRole('combobox', { name: '다른 끝' }), GATE);
    expect(adding.getByText('이 두 장소를 잇는 길이 이미 있습니다.')).toBeInTheDocument();
    await userEvent.selectOptions(adding.getByRole('combobox', { name: '다른 끝' }), CRYPT);
    await userEvent.click(adding.getByRole('checkbox', { name: '양쪽으로 다닌다' }));
    await userEvent.selectOptions(adding.getByRole('combobox', { name: '언제 아는가' }), 'hidden');
    expect(adding.getByRole('button', { name: '더하기' })).toBeDisabled();
    await userEvent.selectOptions(adding.getByRole('combobox', { name: '찾는 판정의 능력치' }), 'dex');
    await userEvent.click(adding.getByRole('button', { name: '더하기' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect((patches(seen)[0]?.routes as RouteRule[])[1]).toEqual({
      from_place: TOWER,
      to_place: CRYPT,
      two_way: false,
      visibility: 'hidden',
      find: { ability: 'dex', difficulty: null },
      travel_minutes: null,
      cross: null,
      lock: null,
      bar: null,
      force: null,
    });

    await userEvent.click(routes.getByRole('button', { name: '수도원 문–종탑 길 고치기' }));
    const editing = within(await screen.findByRole('dialog'));
    await userEvent.selectOptions(editing.getByRole('combobox', { name: '언제 아는가' }), 'fog');
    await userEvent.click(editing.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1]?.routes as RouteRule[])[0]).toEqual({ ...GATE_TOWER, visibility: 'fog' });

    await userEvent.click(routes.getByRole('button', { name: '종탑–지하 묘지 길 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(3));
    expect(patches(seen)[2]?.routes as RouteRule[]).toHaveLength(1);
  });
});

describe('지도 입력', () => {
  it('맵의 장소와 장소의 한 줄, 장소를 비우면 셋에서 빠진다', () => {
    const detail = scenario({ landmarks: [CRYPT], covers: [{ place_id: CRYPT, cover: 3 }] }) as unknown as ScenarioDetail;
    expect([...mapPlaces(detail)].sort()).toEqual([GATE, TOWER, CRYPT].sort());
    expect(placeLine(detail, CRYPT)).toBe('명소 · 커버 3');
    expect(applyPlace(detail, CRYPT, { landmark: false, cover: '', people: [], items: [] })).toEqual({
      landmarks: [],
      covers: [],
      npc_places: [{ entry_id: KEEPER, place_id: GATE }],
      place_items: [],
    });
  });

  it('길: 같은 끝, 빗장이 있는 끝, 시간, 숨김이 아니면 찾는 판정을 싣지 않는다', () => {
    const barred = { ...GATE_TOWER, bar: { side: GATE, barred: false } } as unknown as RouteRule;
    expect(routeHints({ ...routeDraft(null), from: GATE, to: GATE }, [], null).ends).toBe('길의 두 끝이 같은 장소입니다.');
    expect(routeHints({ ...routeDraft(barred), from: TOWER, to: CRYPT }, [barred], 0).ends).toContain('빗장');
    expect(routeHints({ ...routeDraft(barred), minutes: '0' }, [barred], 0).minutes).toBeDefined();
    expect(toRoute({ ...routeDraft(null), from: GATE, to: CRYPT, findAbility: 'dex' }, null).find).toBeNull();
  });
});
