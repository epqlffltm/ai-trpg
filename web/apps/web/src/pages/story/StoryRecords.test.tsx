// web/apps/web/src/pages/story/StoryRecords.test.tsx
// 지도(D3)와 기록(D6). 지도는 지금 있는 곳·함께 다니는 인물·바로 갈 곳(분, 닿는 시각, 거기 보이는 인물)·그 밖에 아는 곳(가 본 곳)을 보인다.
// 기록은 본 엔딩(이름, 처음 본 때)과 못 본 엔딩("???", 힌트), 엔딩 n/m, 이 가지에서 열린 이벤트를 보인다. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';
import { endingCount, endingRows, eventRows } from './storyRecords';
import { arrivalText, clockAt, companionNames, knownPlaces } from './storyMapView';

const SESSION = '00000000-0000-4000-8000-00000000ab01';
const WORLD = '00000000-0000-4000-8000-00000000bb01';
const SPRING = '00000000-0000-4000-8000-0000000000f1';
const RAIN = '00000000-0000-4000-8000-0000000000f2';
const M = (n: number) => `00000000-0000-4000-8000-0000000fb0${n}`;
const AT = '2026-10-27T03:00:00Z';

const VIEW = storyView({
  slots: [
    { id: 'morning', name: '아침', start_hour: 8 },
    { id: 'evening', name: '저녁', start_hour: 18 },
    { id: 'night', name: '밤', start_hour: 21 },
  ],
  places: [
    { id: 'school', name: '학교', description: '', image_id: null, backgrounds: {} },
    { id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} },
    { id: 'shop', name: '가게', description: '', image_id: null, backgrounds: {} },
    { id: 'hill', name: '언덕', description: '', image_id: null, backgrounds: {} },
  ],
  paths: [
    { a: 'school', b: 'park', minutes: 20 },
    { a: 'shop', b: 'school', minutes: 240 },
    { a: 'park', b: 'hill', minutes: 30 },
  ],
  cast: [castOut('mina', '미나'), castOut('jun', '준'), castOut('veil', null)],
  map: [
    { id: 'school', visited: true, cast: [] },
    { id: 'park', visited: true, cast: ['mina'] },
    { id: 'shop', visited: false, cast: [] },
    { id: 'hill', visited: true, cast: ['veil'] },
  ],
  events: [{ id: 'rain', name: '소나기', image_id: RAIN, cast: ['mina'], choices: [] }],
  endings: [
    { id: 'spring', name: '봄의 약속', hint: '', image_id: SPRING, seen: true, unlock: true },
    { id: 'alone', name: null, hint: '아무도 만나지 않는다', image_id: null, seen: false, unlock: true },
    { id: 'joke', name: '농담', hint: '', image_id: null, seen: true, unlock: false },
  ],
});

/** 3일째 19시(저녁) */
function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 2 * 1440 + 19 * 60, day: 3, slot: 'evening', place: 'school', items: {}, affection: {}, companions: ['jun'], choosing: null, ending: null, cast: [], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function session(): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: null, text: '저녁이다.' }] })],
    state: state(),
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

function signedIn() {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session()),
    'GET /api/v1/story/endings': () => json(200, { items: [{ ending_id: 'spring', first_seen_at: AT, conversation_id: SESSION }] }),
    [`GET /api/v1/asset/images/${SPRING}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${RAIN}`]: () => new Response('png', { status: 200 }),
  });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('지도와 기록', () => {
  it('지도에 함께 다니는 인물, 갈 곳의 닿는 시각과 거기 보이는 인물, 그 밖에 아는 곳을 보인다', async () => {
    signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '지도' }));
    const map = within(screen.getByRole('dialog', { name: '지도' }));
    expect(map.getByText('함께: 준')).toBeInTheDocument();
    const reachable = within(map.getByRole('list', { name: '갈 수 있는 곳' }));
    expect(reachable.getByText('저녁 그대로 · 있음: 미나')).toBeInTheDocument();
    expect(reachable.getByText('저녁 → 밤')).toBeInTheDocument();
    const known = within(map.getByRole('list', { name: '아는 곳' }));
    expect(known.getByText('언덕')).toBeInTheDocument();
    expect(known.getByText('가 본 곳 · 있음: ???')).toBeInTheDocument();
    expect(known.queryByText('학교')).toBeNull();
  });

  it('기록에 본 엔딩과 못 본 엔딩, 엔딩 n/m, 열린 이벤트를 보인다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await screen.findByRole('button', { name: '기록' }));
    const records = within(screen.getByRole('dialog', { name: '기록' }));
    expect(await records.findByText(/엔딩 1\/2/)).toBeInTheDocument();
    const endings = within(records.getByRole('list', { name: '엔딩' }));
    expect(endings.getByText('봄의 약속')).toBeInTheDocument();
    expect(endings.getByText(/처음 본 때/)).toBeInTheDocument();
    expect(endings.getByText('???')).toBeInTheDocument();
    expect(endings.getByText('아무도 만나지 않는다')).toBeInTheDocument();
    expect(endings.getByText('기록에 남지 않는 엔딩')).toBeInTheDocument();
    expect(await endings.findByRole('img', { name: '봄의 약속' })).toBeInTheDocument();
    const events = within(records.getByRole('list', { name: '열린 이벤트' }));
    expect(events.getByText('소나기')).toBeInTheDocument();
    expect(seen.some((request) => request.url.startsWith('/api/v1/story/endings'))).toBe(true);
  });
});

describe('순수한 함수', () => {
  it('시각, 닿는 시각, 아는 곳, 함께, 엔딩, 이벤트', () => {
    expect(clockAt(VIEW, 0)).toEqual({ day: 1, slot: 'night' });
    expect(clockAt(VIEW, 8 * 60)).toEqual({ day: 1, slot: 'morning' });
    expect(clockAt(storyView(), 0)).toEqual({ day: 1, slot: null });
    expect(arrivalText(VIEW, state(), 240)).toBe('저녁 → 밤');
    expect(arrivalText(VIEW, state(), 6 * 60)).toBe('저녁 → 4일째 밤');
    expect(arrivalText(VIEW, state(), 14 * 60)).toBe('저녁 → 4일째 아침');
    expect(knownPlaces(VIEW, state()).map((place) => [place.id, place.here, place.cast])).toEqual([
      ['school', true, []],
      ['park', false, ['미나']],
      ['shop', false, []],
      ['hill', false, ['???']],
    ]);
    expect(companionNames(VIEW, state())).toEqual(['준']);
    const rows = endingRows(VIEW, undefined);
    expect(rows.map((row) => [row.name, row.imageId, row.firstSeenAt])).toEqual([
      ['봄의 약속', SPRING, null],
      ['???', null, null],
      ['농담', null, null],
    ]);
    expect(endingCount(VIEW, undefined)).toBeNull();
    expect(endingCount(VIEW, { items: [{ ending_id: 'joke', first_seen_at: AT, conversation_id: null }] })).toBe('엔딩 0/2');
    expect(endingCount(storyView(), { items: [] })).toBeNull();
    expect(eventRows(VIEW)).toEqual([{ id: 'rain', name: '소나기', imageId: RAIN }]);
  });
});
