// web/apps/web/src/pages/trpg/studio/scenarios/Doors.test.tsx
// 지도의 둘째 조각(B9, #281·#279). 길의 문(넘기와 피해, 자물쇠와 따기, 빗장, 부수기, 고치기와 도구)을 창에서 바로 보내기,
// 다른 길의 열쇠 막기, 부수기와 고치기는 자물쇠나 빗장과 함께. 길을 고쳐도 고치기는 남는다. 장소에 놓인 물건(보임과 숨김, 찾는 판정). 입력의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { RouteRule } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { doorDraft, doorHints, withDoor } from './doorForm';
import { placeHints } from './placesForm';
import { routeDraft, routeLine, toRoute } from './routesForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GATE = '00000000-0000-4000-8000-00000000c001';
const TOWER = '00000000-0000-4000-8000-00000000c002';
const CRYPT = '00000000-0000-4000-8000-00000000c003';
const KEY = '00000000-0000-4000-8000-00000000a009';
const PICK = '00000000-0000-4000-8000-00000000a010';
const COIN = '00000000-0000-4000-8000-00000000a011';
const HAMMER = '00000000-0000-4000-8000-00000000a012';

function route(from: string, to: string, extra: Record<string, unknown> = {}) {
  return { from_place: from, to_place: to, two_way: true, visibility: 'open', find: null, travel_minutes: null, cross: null, lock: null, bar: null, force: null, ...extra };
}

const LOCKED = route(GATE, TOWER, { lock: { key: KEY, locked: true, pick: null }, repair: { ability: 'dex', difficulty: null, needs_tool: false } });
const PLAIN = route(TOWER, CRYPT);

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function signedIn(start: Record<string, unknown> = {}) {
  let current = scenarioDetail({ rulebook_id: RULEBOOK, lorebook_ids: [LOREBOOK], start_place: GATE, routes: [LOCKED, PLAIN], ...start });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [
        entry(GATE, '수도원 문', 'place'),
        entry(TOWER, '종탑', 'place'),
        entry(CRYPT, '지하 묘지', 'place'),
        entry(KEY, '녹슨 열쇠', 'item'),
        entry(PICK, '쇠꼬챙이', 'item'),
        entry(COIN, '은화 주머니', 'item'),
        entry(HAMMER, '망치', 'item'),
      ]),
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

describe('길의 문', () => {
  it('넘기·자물쇠·따기·빗장·부수기를 창에서 정하면 그 길의 문만 바꿔 보낸다. 다른 길의 열쇠는 막는다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const routes = within(await (await mapPanel()).findByRole('list', { name: '길' }));
    await userEvent.click(routes.getByRole('button', { name: '종탑–지하 묘지 길의 문' }));
    const dialog = within(await screen.findByRole('dialog'));
    expect(dialog.getByRole('checkbox', { name: '문을 부술 수 있다' })).toBeDisabled();
    expect(dialog.getByRole('checkbox', { name: '부서진 문을 고칠 수 있다' })).toBeDisabled();

    await userEvent.click(dialog.getByRole('checkbox', { name: '지날 때마다 판정한다' }));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '넘기 판정의 능력치' }), 'str');
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '넘기 판정에 실패하면 다치는 양' }), 'light');

    await userEvent.click(dialog.getByRole('checkbox', { name: '자물쇠가 있다' }));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '열쇠' }), KEY);
    expect(dialog.getByText('이 열쇠는 다른 길의 자물쇠를 엽니다. 열쇠 하나는 자물쇠 하나만 엽니다.')).toBeInTheDocument();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '열쇠' }), COIN);
    await userEvent.click(dialog.getByRole('checkbox', { name: '열쇠 없이 딸 수 있다' }));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '따기 판정의 능력치' }), 'dex');
    await userEvent.click(dialog.getByRole('checkbox', { name: '도구가 있어야 딴다' }));

    await userEvent.click(dialog.getByRole('checkbox', { name: '빗장이 있다' }));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '빗장이 있는 쪽' }), CRYPT);
    await userEvent.click(dialog.getByRole('checkbox', { name: '문을 부술 수 있다' }));
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '부수기 판정의 능력치' }), 'str');
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '부수기 판정의 난이도' }), 'normal');
    await userEvent.click(dialog.getByRole('checkbox', { name: '부서진 문을 고칠 수 있다' }));
    expect(dialog.getByText('고치기 판정의 능력치를 골라 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '고치기 판정의 능력치' }), 'dex');
    await userEvent.click(dialog.getByRole('checkbox', { name: '도구가 있어야 고친다' }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const sent = patches(seen)[0]?.routes as RouteRule[];
    expect(sent[0]).toEqual(LOCKED);
    expect(sent[1]).toEqual({
      ...PLAIN,
      cross: { ability: 'str', difficulty: null, harm: 'light' },
      lock: { key: COIN, locked: true, pick: { ability: 'dex', difficulty: null, needs_tool: true } },
      bar: { side: CRYPT, barred: false },
      force: { ability: 'str', difficulty: 'normal' },
      repair: { ability: 'dex', difficulty: null, needs_tool: true },
    });
    expect(
      await routes.findByText('종탑 ↔ 지하 묘지 · 처음부터 앎 · 넘기 판정 · 자물쇠(잠김, 딸 수 있음) · 빗장(지하 묘지 쪽) · 부술 수 있음 · 고칠 수 있음'),
    ).toBeInTheDocument();
  });

  it('장소에 숨긴 물건을 놓으면 찾는 판정과 함께 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=map`);

    const places = within(await (await mapPanel()).findByRole('list', { name: '장소' }));
    await userEvent.click(places.getByRole('button', { name: '지하 묘지 고치기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '놓인 물건 더하기' }));
    const line = within(dialog.getByRole('group', { name: '놓인 물건 1' }));
    await userEvent.selectOptions(line.getByRole('combobox', { name: '물건' }), COIN);
    await userEvent.selectOptions(line.getByRole('combobox', { name: '보이는가' }), 'hidden');
    expect(line.getByText('숨긴 물건은 찾는 판정의 능력치를 골라 주세요.')).toBeInTheDocument();
    await userEvent.selectOptions(line.getByRole('combobox', { name: '찾는 판정의 능력치' }), 'dex');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.place_items).toEqual([
      { place_id: CRYPT, entry_id: COIN, count: 1, visibility: 'hidden', find: { ability: 'dex', difficulty: null } },
    ]);
    expect(await places.findByText('길 1 · 물건 1(숨김 1)')).toBeInTheDocument();
  });
});

describe('길의 문 입력', () => {
  it('끈 것은 null, 부수기와 고치기는 자물쇠나 빗장과 함께, 빗장은 두 끝 중 하나', () => {
    const routes = [LOCKED, PLAIN] as unknown as RouteRule[];
    const draft = doorDraft(routes[0] as RouteRule);
    expect(draft.repair).toEqual({ on: true, ability: 'dex', difficulty: '', needsTool: false });
    expect(withDoor(routes, 0, { ...draft, lock: { ...draft.lock, on: false } })[0]).toMatchObject({ lock: null, force: null, repair: null });
    expect(doorHints({ ...draft, lock: { ...draft.lock, on: false } }, routes, 0).repair).toContain('자물쇠나 빗장');
    expect(toRoute({ ...routeDraft(routes[0] as RouteRule), minutes: '5' }, routes[0] as RouteRule).repair).toEqual({ ability: 'dex', difficulty: null, needs_tool: false });
    expect(doorHints({ ...draft, lock: { ...draft.lock, on: false }, force: { on: true, ability: 'str', difficulty: '' } }, routes, 0).force).toContain('자물쇠나 빗장');
    expect(doorHints({ ...draft, bar: { on: true, side: CRYPT, barred: false } }, routes, 0).bar).toBeDefined();
    expect(routeLine({ ...LOCKED, bar: { side: GATE, barred: true } } as unknown as RouteRule, (id) => (id === GATE ? '문' : '탑'), null)).toBe(
      '문 ↔ 탑 · 처음부터 앎 · 자물쇠(잠김) · 빗장(문 쪽, 걸림) · 고칠 수 있음',
    );
  });

  it('놓인 물건: 같은 물건은 같은 보이기로 한 줄, 보이기가 다르면 두 줄도 된다', () => {
    const line = { entryId: COIN, count: '1', visibility: 'open' as const, findAbility: '', findDifficulty: '' };
    expect(placeHints({ landmark: false, cover: '', people: [], items: [line, line] })['item.1']).toContain('같은 물건');
    expect(placeHints({ landmark: false, cover: '', people: [], items: [line, { ...line, visibility: 'hidden', findAbility: 'dex' }] })).toEqual({});
  });
});
