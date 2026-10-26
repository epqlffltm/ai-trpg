// web/apps/web/src/pages/trpg/studio/scenarios/LockItems.test.tsx
// 자물쇠 물건(#281, B9 물건·돈). 물건 규칙 창에서 장비를 새 자물쇠로 두고(새 열쇠, 따기와 도구) 보내기,
// 자기 자신과 다른 자물쇠의 열쇠 막기, 창을 다시 저장해도 자물쇠가 남기, 소모품이면 보내지 않기.
// 길의 문의 열쇠도 자물쇠 물건의 열쇠와 겹치지 못한다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import type { ItemRule, RouteRule } from '../../../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { doorDraft, doorHints } from './doorForm';
import { itemLockHints, keysElsewhere } from './itemLockForm';
import { itemRuleDraft, itemRuleLine, toItemRule } from './itemRuleForm';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const SCENARIO = `${GAME}/scenarios/${ID}`;
const GATE = '00000000-0000-4000-8000-00000000c001';
const TOWER = '00000000-0000-4000-8000-00000000c002';
const PADLOCK = '00000000-0000-4000-8000-00000000a020';
const OLD_KEY = '00000000-0000-4000-8000-00000000a021';
const NEW_KEY = '00000000-0000-4000-8000-00000000a022';
const PICK = '00000000-0000-4000-8000-00000000a023';

const ROUTE = { from_place: GATE, to_place: TOWER, two_way: true, visibility: 'open', find: null, travel_minutes: null, cross: null, lock: { key: OLD_KEY, locked: true, pick: null }, bar: null, force: null, repair: null };

function entry(id: string, name: string, kind: string) {
  return { id, name, kind, keywords: [], content: '', true_names: [], created_at: '', updated_at: '' };
}

function signedIn() {
  let current = scenarioDetail({ rulebook_id: RULEBOOK, lorebook_ids: [LOREBOOK], start_place: GATE, routes: [ROUTE] });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () => json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', rules: RULES }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [entry(PADLOCK, '새 자물쇠', 'item'), entry(OLD_KEY, '녹슨 열쇠', 'item'), entry(NEW_KEY, '은 열쇠', 'item'), entry(PICK, '쇠꼬챙이', 'item')]),
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

afterEach(() => {
  vi.restoreAllMocks();
});

describe('자물쇠 물건', () => {
  it('장비를 새 자물쇠로 두고 새 열쇠와 따기를 보낸다. 자기 자신은 열쇠 목록에 없고, 길의 열쇠는 막는다. 다시 저장해도 남는다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=items`);

    const panel = within(await screen.findByRole('tabpanel', { name: '물건·돈' }));
    const list = within(await panel.findByRole('list', { name: '물건 규칙' }));
    await userEvent.click(list.getByRole('button', { name: '새 자물쇠 규칙 고치기' }));
    let dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('checkbox', { name: '문에 다는 새 자물쇠다' }));
    expect(within(dialog.getByRole('combobox', { name: '새 열쇠' })).queryByRole('option', { name: '새 자물쇠' })).toBeNull();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '새 열쇠' }), OLD_KEY);
    expect(dialog.getByText(/이 열쇠는 다른 자물쇠\(길의 자물쇠나 자물쇠 물건\)를 엽니다/)).toBeInTheDocument();
    expect(dialog.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '새 열쇠' }), NEW_KEY);
    await userEvent.click(dialog.getByRole('checkbox', { name: '열쇠 없이 딸 수 있다' }));
    await userEvent.selectOptions(dialog.getByRole('combobox', { name: '따기 판정의 능력치' }), 'dex');
    await userEvent.click(dialog.getByRole('checkbox', { name: '도구가 있어야 딴다' }));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    const lock = { key: NEW_KEY, pick: { ability: 'dex', difficulty: null, needs_tool: true } };
    expect((patches(seen)[0]?.items as ItemRule[])[0]).toMatchObject({ entry_id: PADLOCK, kind: 'gear', lock });
    expect(await list.findByText(/새 자물쇠\(딸 수 있음\)/)).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '새 자물쇠 규칙 고치기' }));
    dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect((patches(seen)[1]?.items as ItemRule[])[0]?.lock).toEqual(lock);
  });
});

describe('자물쇠 물건의 입력', () => {
  it('열쇠는 꼭, 자기 자신은 안 됨, 다른 자물쇠와 겹치지 않음, 따기는 능력치를 꼭. 소모품이면 보내지 않는다', () => {
    const routes = [ROUTE] as unknown as RouteRule[];
    const others = [{ entry_id: 'x', kind: 'gear', lock: { key: NEW_KEY, pick: null } }] as unknown as ItemRule[];
    const draft = itemRuleDraft(undefined);
    const lock = { ...draft.lock, on: true };
    expect(itemLockHints(lock, PADLOCK, []).lock).toContain('열쇠(물건)를 골라');
    expect(itemLockHints({ ...lock, key: PADLOCK }, PADLOCK, []).lock).toContain('자물쇠 물건 자신은');
    expect(keysElsewhere(routes, others, PADLOCK)).toEqual([OLD_KEY, NEW_KEY]);
    expect(keysElsewhere(routes, others, 'x')).toEqual([OLD_KEY]);
    expect(itemLockHints({ ...lock, key: PICK, pick: { on: true, ability: '', difficulty: '', needsTool: false } }, PADLOCK, []).lock_pick).toBeDefined();
    const withLock = { ...draft, lock: { ...lock, key: NEW_KEY } };
    expect(toItemRule(PADLOCK, withLock).lock).toEqual({ key: NEW_KEY, pick: null });
    expect(toItemRule(PADLOCK, { ...withLock, kind: 'consumable' }).lock).toBeNull();
    expect(itemRuleLine({ ...toItemRule(PADLOCK, withLock), lock: { key: NEW_KEY, pick: null } } as ItemRule, null)).toBe('장비 · 보통 · 새 자물쇠');
  });

  it('길의 문의 열쇠도 자물쇠 물건의 열쇠와 겹치지 못한다', () => {
    const routes = [ROUTE] as unknown as RouteRule[];
    const draft = doorDraft(routes[0] as RouteRule);
    expect(doorHints({ ...draft, lock: { ...draft.lock, key: NEW_KEY } }, routes, 0, [NEW_KEY]).lock).toContain('자물쇠 물건의 새 자물쇠');
    expect(doorHints(draft, routes, 0, [NEW_KEY]).lock).toBeUndefined();
  });
});
