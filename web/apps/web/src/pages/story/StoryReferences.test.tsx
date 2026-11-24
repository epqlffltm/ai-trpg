// web/apps/web/src/pages/story/StoryReferences.test.tsx
// 장면(D2)의 참고 자료 쓰기(#1338). 왼쪽 열의 페르소나·모델 창에 있다. 세계관이 허용했을 때만 보이고,
// 켜고 끄면 PUT /references 를 보내고 읽어 둔 세션의 칸만 바꾼다. 받는 중에는 막는다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StorySession } from '../../api/story';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';

const WORLD = '00000000-0000-4000-8000-00000000bf01';
const SESSION = '00000000-0000-4000-8000-00000000af01';
const AT = '2026-10-27T03:00:00Z';
const REFERENCES = `/api/v1/story/conversations/${SESSION}/references`;

function session(allowed: boolean, enabled: boolean): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy' },
    view: storyView({ slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} }] }),
    persona: null,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [],
    state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'school', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
    references_allowed: allowed,
    references_enabled: enabled,
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/asset/personas': () => json(200, []),
    [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', tags: [], deadline_days: null, published_at: AT, intro_html: '', after_ending: 'end', ending_count: 0, cast: [] }),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/story/endings': () => json(200, { items: [] }),
    ...routes,
  });
}

/** 왼쪽 열의 페르소나·모델 창을 펼친다. 창 안에서 찾는 within 을 돌려준다 */
async function personaPanel() {
  const column = within(await screen.findByRole('region', { name: '창' }));
  await userEvent.click(column.getByRole('button', { name: '페르소나·모델' }));
  return within(column.getByRole('region', { name: '페르소나·모델' }));
}

function sent(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('세션의 참고 자료', () => {
  it('허용한 세계관이면 켜고 끈다', async () => {
    let current = session(true, false);
    const { seen } = signedIn({
      [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, current),
      [`PUT ${REFERENCES}`]: (request) => {
        const { enabled } = request.body as { enabled: boolean };
        current = session(true, enabled);
        return json(200, { enabled });
      },
    });
    renderApp(`/story/sessions/${SESSION}`);

    const panel = await personaPanel();
    const toggle = panel.getByRole('checkbox', { name: '참고 자료 쓰기' });
    expect(toggle).not.toBeChecked();
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toBeChecked());
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).not.toBeChecked());

    expect(sent(seen, 'PUT', REFERENCES)).toEqual([{ enabled: true }, { enabled: false }]);
  });

  it('허용하지 않은 세계관이면 보이지 않는다', async () => {
    signedIn({ [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session(false, false)) });
    renderApp(`/story/sessions/${SESSION}`);

    const panel = await personaPanel();
    expect(panel.getByRole('button', { name: '페르소나 바꾸기' })).toBeInTheDocument();
    expect(panel.queryByRole('checkbox', { name: '참고 자료 쓰기' })).toBeNull();
  });

  it('바꾸지 못하면 까닭을 적는다', async () => {
    signedIn({
      [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session(true, true)),
      [`PUT ${REFERENCES}`]: () => json(500, { detail: '서버 오류' }),
    });
    renderApp(`/story/sessions/${SESSION}`);

    const panel = await personaPanel();
    const toggle = panel.getByRole('checkbox', { name: '참고 자료 쓰기' });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);

    expect(await panel.findByText('참고 자료를 바꾸지 못했습니다. 잠시 뒤에 다시 시도하세요.')).toBeInTheDocument();
    expect(toggle).toBeChecked();
  });
});
