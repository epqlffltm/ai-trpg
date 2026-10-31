// web/apps/web/src/pages/story/StoryNotes.test.tsx
// 장면(D2)의 기억 창. 행동 줄의 "기억"으로 열고, 기억 메모를 보고 더하고 고치고 지운다. 가득 차면(409 notes_full) 까닭을 알린다.
// 앞의 줄거리(요약)는 읽기만 하고, 없으면 안내한다. 요약이 제안한 메모는 따로 보이고 받아들이거나 버린다.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StorySession } from '../../api/story';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { storyView } from '../../test/storyFixtures';

const SESSION = '00000000-0000-4000-8000-00000000ae21';
const WORLD = '00000000-0000-4000-8000-00000000be21';
const NOTES = `/api/v1/story/conversations/${SESSION}/notes`;
const AT = '2026-10-29T03:00:00Z';
const N = (n: number) => `00000000-0000-4000-8000-0000000fe1${n}`;

function session(): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', genre: 'fantasy' },
    view: storyView({ slots: [{ id: 'morning', name: '아침', start_hour: 7 }], places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }] }),
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [],
    state: { minutes: 7 * 60, day: 1, slot: 'morning', place: 'park', items: {}, affection: {}, companions: [], choosing: null, ending: null, cast: [] },
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function note(n: number, text: string, pending = false): { id: string; text: string; source: string; pending: boolean; accepted_at: string | null; created_at: string; updated_at: string } {
  return { id: N(n), text, source: pending ? 'summary' : 'user', pending, accepted_at: null, created_at: AT, updated_at: AT };
}

function signedIn(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  let notes = [note(1, '미나는 고양이를 무서워한다')];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session()),
    [`GET /api/v1/story/conversations/${SESSION}/summary`]: () => json(200, null),
    [`GET ${NOTES}`]: () => json(200, notes),
    [`POST ${NOTES}`]: (request) => {
      const added = note(2, (request.body as { text: string }).text);
      notes = [...notes, added];
      return json(201, added);
    },
    [`PATCH ${NOTES}/${N(1)}`]: (request) => {
      notes = notes.map((entry) => (entry.id === N(1) ? { ...entry, text: (request.body as { text: string }).text } : entry));
      return json(200, notes[0]);
    },
    [`DELETE ${NOTES}/${N(1)}`]: () => {
      notes = notes.filter((entry) => entry.id !== N(1));
      return new Response(null, { status: 204 });
    },
    ...routes,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('기억 창', () => {
  it('요약이 제안한 메모를 받아들이면 메모가 되고, 버리면 지운다', async () => {
    let notes = [note(1, '미나는 고양이를 무서워한다'), note(3, '불꽃놀이는 30일째다', true), note(4, '준은 수영부다', true)];
    const { seen } = signedIn({
      [`GET ${NOTES}`]: () => json(200, notes),
      [`POST ${NOTES}/${N(3)}/accept`]: () => {
        notes = notes.map((entry) => (entry.id === N(3) ? { ...entry, pending: false, accepted_at: AT } : entry));
        return json(200, notes[1]);
      },
      [`DELETE ${NOTES}/${N(4)}`]: () => {
        notes = notes.filter((entry) => entry.id !== N(4));
        return new Response(null, { status: 204 });
      },
    });
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '기억' }));
    const dialog = within(screen.getByRole('dialog', { name: '기억' }));
    const suggested = within(await dialog.findByRole('list', { name: '요약이 제안한 메모' }));
    expect(dialog.getByText('1 / 20')).toBeInTheDocument();
    await userEvent.click(within(suggested.getByText('불꽃놀이는 30일째다').closest('li') as HTMLElement).getByRole('button', { name: '받아들이기' }));
    expect(await within(dialog.getByRole('list', { name: '기억 메모' })).findByText('불꽃놀이는 30일째다')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '버리기: 준은 수영부다' }));
    await waitFor(() => expect(dialog.queryByRole('list', { name: '요약이 제안한 메모' })).toBeNull());
    expect(seen.filter((request) => request.method !== 'GET' && request.url.startsWith(NOTES)).map((request) => `${request.method} ${request.url.slice(NOTES.length)}`)).toEqual([`POST /${N(3)}/accept`, `DELETE /${N(4)}`]);
  });

  it('메모를 보고 더하고 고치고 지운다. 요약이 없으면 안내한다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '기억' }));
    const dialog = within(screen.getByRole('dialog', { name: '기억' }));
    const list = within(await dialog.findByRole('list', { name: '기억 메모' }));
    expect(list.getByText('미나는 고양이를 무서워한다')).toBeInTheDocument();
    expect(dialog.getByText('1 / 20')).toBeInTheDocument();
    expect(dialog.getByText(/아직 요약이 없습니다/)).toBeInTheDocument();
    expect(dialog.queryByText('요약이 제안한 메모')).toBeNull();

    await userEvent.type(dialog.getByLabelText('새 메모'), '불꽃놀이를 약속했다');
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));
    expect(await list.findByText('불꽃놀이를 약속했다')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '고치기: 미나는 고양이를 무서워한다' }));
    const edit = dialog.getByLabelText('고칠 메모');
    await userEvent.clear(edit);
    await userEvent.type(edit, '미나는 고양이를 좋아한다');
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));
    expect(await list.findByText('미나는 고양이를 좋아한다')).toBeInTheDocument();

    await userEvent.click(list.getByRole('button', { name: '지우기: 미나는 고양이를 좋아한다' }));
    await waitFor(() => expect(list.queryByText('미나는 고양이를 좋아한다')).toBeNull());
    expect(seen.filter((request) => request.method !== 'GET' && request.url.startsWith(NOTES)).map((request) => `${request.method} ${request.body ? JSON.stringify(request.body) : ''}`)).toEqual([
      'POST {"text":"불꽃놀이를 약속했다"}',
      'PATCH {"text":"미나는 고양이를 좋아한다"}',
      'DELETE ',
    ]);
  });

  it('가득 차면 까닭을 알리고, 요약이 있으면 보인다', async () => {
    signedIn({
      [`POST ${NOTES}`]: () => json(409, { detail: 'x', code: 'notes_full' }),
      [`GET /api/v1/story/conversations/${SESSION}/summary`]: () => json(200, { text: '여름이 시작됐다.', covered_up_to: N(9), created_at: AT }),
    });
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '기억' }));
    const dialog = within(screen.getByRole('dialog', { name: '기억' }));
    expect(await dialog.findByText('여름이 시작됐다.')).toBeInTheDocument();
    await userEvent.type(await dialog.findByLabelText('새 메모'), '하나 더');
    await userEvent.click(dialog.getByRole('button', { name: '더하기' }));
    expect(await dialog.findByText('기억 메모는 20개까지입니다. 지우고 더해 주세요.')).toBeInTheDocument();
  });
});
