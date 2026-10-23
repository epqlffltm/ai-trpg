// web/apps/web/src/pages/trpg/studio/worlds/Worlds.test.tsx
// 세계관(B9). 만들기 허브에서 목록으로, 만들기의 본문과 고치기로 넘어감, 고치기의 PATCH 본문, 길이 검사,
// 쓰는 시나리오가 있어 지우지 못함(409), 없는 세계관을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { ME } from '../../../../test/tableFixtures';
import { newWorldDraft, SETTING_MAX, toWorldCreate, worldHints } from './worldForm';

const BASE = '/api/v1/game/worlds';
const ID = '00000000-0000-4000-8000-0000000000c2';

function world(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    title: '안개 대륙',
    description: '',
    setting: '안개가 걷히지 않는 땅.',
    gm_notes: '안개는 용의 숨이다.',
    references_allowed: false,
    visibility: 'private',
    created_at: '2026-10-23T00:00:00Z',
    updated_at: '2026-10-23T00:00:00Z',
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${BASE}`]: () => json(200, { items: [], total: 0 }),
    [`GET ${BASE}/${ID}`]: () => json(200, world()),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === `${BASE}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('세계관', () => {
  it('허브에서 빈 목록으로, 만들면 그 세계관의 고치기로 간다', async () => {
    const { seen } = signedIn({ [`POST ${BASE}`]: () => json(201, world()) });
    renderApp('/trpg/studio');

    await userEvent.click(await screen.findByRole('link', { name: '내 세계관' }));
    await userEvent.click(await screen.findByRole('link', { name: '첫 세계관 만들기' }));
    const form = within(await screen.findByRole('form', { name: '세계관' }));
    await userEvent.type(form.getByLabelText('제목'), ' 안개 대륙 ');
    await userEvent.type(form.getByLabelText('설정(선택)'), '안개가 걷히지 않는 땅.');
    await userEvent.click(form.getByRole('checkbox', { name: /참고 자료를 켤 수 있게/ }));
    await userEvent.click(form.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '안개 대륙' })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', '')[0]?.body).toEqual({
      title: '안개 대륙',
      description: '',
      setting: '안개가 걷히지 않는 땅.',
      gm_notes: '',
      references_allowed: true,
    });
  });

  it('고치면 모든 칸을 PATCH 로 보내고 저장했다고 알린다', async () => {
    const { seen } = signedIn({ [`PATCH ${BASE}/${ID}`]: () => json(200, world({ gm_notes: '', updated_at: '2026-10-23T01:00:00Z' })) });
    renderApp(`/trpg/studio/worlds/${ID}`);

    const form = within(await screen.findByRole('form', { name: '세계관' }));
    expect(form.getByLabelText('GM 메모(선택)')).toHaveValue('안개는 용의 숨이다.');
    await userEvent.clear(form.getByLabelText('GM 메모(선택)'));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    expect(await screen.findByText('저장했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'PATCH', `/${ID}`)[0]?.body).toEqual({
      title: '안개 대륙',
      description: '',
      setting: '안개가 걷히지 않는 땅.',
      gm_notes: '',
      references_allowed: false,
    });
  });

  it('쓰는 시나리오가 있으면 지우지 못하고 그 제목을 알린다', async () => {
    signedIn({ [`DELETE ${BASE}/${ID}`]: () => json(409, { detail: 'x', used_by: [{ id: 's1', title: '안개 마을' }] }) });
    renderApp(`/trpg/studio/worlds/${ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '지우기' }));
    const dialog = within(await screen.findByRole('dialog'));
    await userEvent.click(dialog.getByRole('button', { name: '지우기' }));
    expect(await dialog.findByText(/쓰는 시나리오: 안개 마을/)).toBeInTheDocument();
  });

  it('없거나 남의 세계관이면 찾을 수 없다고 알린다', async () => {
    signedIn({ [`GET ${BASE}/${ID}`]: () => json(404, { detail: 'x' }) });
    renderApp(`/trpg/studio/worlds/${ID}`);
    expect(await screen.findByText('세계관을 찾을 수 없습니다. 지워졌을 수 있습니다.')).toBeInTheDocument();
  });

  it('제목은 공백을 떼고 적어야 하고, 설정은 8,000자까지다', () => {
    const draft = { ...newWorldDraft(), title: '  ' };
    expect(Object.keys(worldHints(draft))).toEqual(['title']);
    expect(worldHints({ ...draft, title: '땅', setting: 'x'.repeat(SETTING_MAX + 1) }).setting).toContain('8000자');
    expect(toWorldCreate({ ...draft, title: ' 땅 ' }).title).toBe('땅');
  });
});
