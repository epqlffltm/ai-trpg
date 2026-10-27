// web/apps/web/src/pages/story/StoryPersona.test.tsx
// story 의 페르소나. 세계관 소개(D1)의 새로 시작에서 "나"를 고르고(기본이 골라져 있다, "페르소나 없이"는 null),
// 장면(D2)의 머리에서 지금 페르소나를 보고 바꾼다(PUT /persona). 내 목록의 판이 더 크면 "새 설정으로 바꾸기"(같은 id).
// 404 persona_not_found 는 세션이 그대로라고 알린다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryPersona, StorySession } from '../../api/story';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';
import { personaLabel, staleRevision } from './storyPersonaView';

const WORLD = '00000000-0000-4000-8000-00000000bf01';
const SESSION = '00000000-0000-4000-8000-00000000af01';
const SUMMER = '00000000-0000-4000-8000-00000000cf01';
const WINTER = '00000000-0000-4000-8000-00000000cf02';
const AT = '2026-10-27T03:00:00Z';
const PERSONA_PATH = `/api/v1/story/conversations/${SESSION}/persona`;

function mine(id: string, name: string, revision: number, isDefault: boolean) {
  return { id, name, revision, is_default: isDefault, age: '', gender: '', description: '', form_of_address: '', personality: '', speech_examples: '', image_id: null, created_at: AT, updated_at: AT };
}

const PERSONAS = [mine(SUMMER, '한여름', 3, true), mine(WINTER, '한겨울', 1, false)];

function copy(id: string, name: string, revision: number): StoryPersona {
  return { id, name, revision, age: '', gender: '', description: '', form_of_address: '', personality: '', speech_examples: '', image_id: null };
}

function session(persona: StoryPersona | null): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' },
    view: storyView({ slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} }] }),
    persona,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [],
    state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'school', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
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
    'GET /api/v1/asset/personas': () => json(200, PERSONAS),
    [`GET /api/v1/asset/listings/worlds/${WORLD}`]: () => json(200, { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', tags: [], deadline_days: null, published_at: AT, intro_html: '', after_ending: 'end', ending_count: 0, cast: [] }),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/story/endings': () => json(200, { items: [] }),
    ...routes,
  });
}

function sent(seen: SeenRequest[], method: string, url: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === url).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('story 의 페르소나', () => {
  it('새로 시작할 때 기본 페르소나가 골라져 있고, "페르소나 없이"는 null 로 보낸다', async () => {
    const { seen } = signedIn({ 'POST /api/v1/story/conversations': () => json(201, session(null)), [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session(null)) });
    renderApp(`/story/worlds/${WORLD}`);

    const select = await screen.findByLabelText('나(페르소나)');
    await within(select).findByRole('option', { name: '한여름(기본)' });
    expect(select).toHaveValue(SUMMER);
    await userEvent.selectOptions(select, '');
    await userEvent.click(screen.getByRole('button', { name: '새로 시작' }));
    await waitFor(() => expect(sent(seen, 'POST', '/api/v1/story/conversations')).toEqual([{ world_id: WORLD, persona_id: null }]));
  });

  it('장면에서 지금 페르소나를 보고, 설정이 바뀌었으면 새 설정으로, 다른 것을 고르면 그것으로 바꾼다', async () => {
    let current = session(copy(SUMMER, '한여름', 2));
    const { seen } = signedIn({
      [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, current),
      [`PUT ${PERSONA_PATH}`]: (request) => {
        const id = (request.body as { persona_id: string | null }).persona_id;
        const persona = id === SUMMER ? copy(SUMMER, '한여름', 3) : id === WINTER ? copy(WINTER, '한겨울', 1) : null;
        current = session(persona);
        return json(200, { persona });
      },
    });
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('나: 한여름')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '페르소나 바꾸기' }));
    const dialog = within(screen.getByRole('dialog', { name: '나(페르소나)' }));
    await userEvent.click(await dialog.findByRole('button', { name: '새 설정으로 바꾸기' }));
    await waitFor(() => expect(sent(seen, 'PUT', PERSONA_PATH)).toEqual([{ persona_id: SUMMER }]));

    await userEvent.click(screen.getByRole('button', { name: '페르소나 바꾸기' }));
    const again = within(screen.getByRole('dialog', { name: '나(페르소나)' }));
    expect(again.queryByRole('button', { name: '새 설정으로 바꾸기' })).toBeNull();
    const select = again.getByLabelText('나(페르소나)');
    await within(select).findByRole('option', { name: '한겨울' });
    await userEvent.selectOptions(select, WINTER);
    await userEvent.click(again.getByRole('button', { name: '이 페르소나로 바꾸기' }));
    expect(await screen.findByText('나: 한겨울')).toBeInTheDocument();
    expect(sent(seen, 'PUT', PERSONA_PATH)).toEqual([{ persona_id: SUMMER }, { persona_id: WINTER }]);
  });

  it('고른 페르소나가 없으면 세션은 그대로라고 알린다', async () => {
    signedIn({
      [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session(null)),
      [`PUT ${PERSONA_PATH}`]: () => json(404, { detail: '페르소나를 찾을 수 없습니다.', code: 'persona_not_found' }),
    });
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByText('나: 페르소나 없음')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '페르소나 바꾸기' }));
    const dialog = within(screen.getByRole('dialog', { name: '나(페르소나)' }));
    const select = dialog.getByLabelText('나(페르소나)');
    await within(select).findByRole('option', { name: '한겨울' });
    await userEvent.selectOptions(select, WINTER);
    await userEvent.click(dialog.getByRole('button', { name: '이 페르소나로 바꾸기' }));
    expect(await dialog.findByText(/세션의 페르소나는 그대로입니다/)).toBeInTheDocument();
    expect(screen.getByText('나: 페르소나 없음')).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  it('이름, 판이 바뀌었나', () => {
    expect(personaLabel(null)).toBe('페르소나 없음');
    expect(personaLabel(undefined)).toBe('페르소나 없음');
    expect(personaLabel({ name: '한여름' })).toBe('한여름');
    expect(staleRevision(PERSONAS, { id: SUMMER, revision: 2 })).toBe(true);
    expect(staleRevision(PERSONAS, { id: SUMMER, revision: 3 })).toBe(false);
    expect(staleRevision(PERSONAS, { id: 'gone', revision: 1 })).toBe(false);
    expect(staleRevision(PERSONAS, null)).toBe(false);
  });
});
