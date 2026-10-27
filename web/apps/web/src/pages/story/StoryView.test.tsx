// web/apps/web/src/pages/story/StoryView.test.tsx
// 장면(D2)의 그림 창과 인물 창(D5). 지금 장소·시간대의 배경, 열린 이벤트의 일러스트, 실루엣 인물("???"),
// 인물 창의 소개·호감도(단계)·고백 대기(고백을 막음)·건넨 선물·함께 본 이벤트, 내 세션 목록의 진행 한 줄. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';
import { affectionText, backgroundOf, clockText, coolingText, portraitOf, progressLine, sceneOf, stageOf } from './storyCastView';

const SESSION = '00000000-0000-4000-8000-00000000aa01';
const WORLD = '00000000-0000-4000-8000-00000000ba01';
const EVENING = '00000000-0000-4000-8000-0000000000e1';
const RAIN = '00000000-0000-4000-8000-0000000000e2';
const MINA = '00000000-0000-4000-8000-0000000000e3';
const M = (n: number) => `00000000-0000-4000-8000-0000000fa0${n}`;
const AT = '2026-10-27T03:00:00Z';

const STAGES = [
  { name: '친구', at: 0 },
  { name: '호감', at: 40 },
  { name: '사랑', at: 60 },
];

const VIEW = storyView({
  deadline_days: 30,
  slots: [{ id: 'evening', name: '저녁', start_hour: 18 }],
  places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: { evening: EVENING } }],
  items: [{ id: 'flower', name: '꽃', description: '', image_id: null, consumable: false }],
  cast: [
    castOut('mina', '미나', {
      confessable: true,
      sprites: [{ id: 's1', expression: '', image_id: MINA }],
      intro_html: '<p>카페의 점원.</p>',
      age: '스물',
      gender: '여성',
      affection: { display: 'stage', stages: STAGES, cooling_until: 3 * 1440 + 7 * 60, gifts: ['flower'] },
      events: ['rain'],
    }),
    castOut('veil', null),
  ],
  events: [{ id: 'rain', name: '소나기', image_id: RAIN, cast: ['mina'], choices: [] }],
});

function state(extra: Partial<StoryState> = {}): StoryState {
  return { minutes: 2 * 1440 + 18 * 60, day: 3, slot: 'evening', place: 'park', items: { flower: 1 }, affection: { mina: 45 }, companions: [], choosing: null, ending: null, cast: ['mina', 'veil'], ...extra };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function session(extra: Partial<StorySession> = {}): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all', document: {} },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages: [message(1, 'user', { content: '안녕?' }), message(2, 'assistant', { segments: [{ speaker: 'mina', text: '안녕.' }] })],
    state: state(),
    created_at: AT,
    updated_at: AT,
    ...extra,
  } as StorySession;
}

function signedIn(current: () => StorySession, routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, current()),
    [`GET /api/v1/asset/images/${EVENING}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${RAIN}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/asset/images/${MINA}`]: () => new Response('png', { status: 200 }),
    ...routes,
  });
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('그림 창과 인물 창', () => {
  it('지금 장소와 시간대의 배경을 띄우고, 실루엣 인물은 ??? 로 둔다', async () => {
    const { seen } = signedIn(() => session());
    renderApp(`/story/sessions/${SESSION}`);

    expect(await screen.findByRole('img', { name: '공원' })).toBeInTheDocument();
    const cast = within(screen.getByRole('region', { name: '장면의 인물' }));
    expect(cast.getByRole('button', { name: '미나' })).toBeInTheDocument();
    expect(cast.getByRole('button', { name: '???' })).toBeInTheDocument();
    expect(seen.some((request) => request.url === `/api/v1/asset/images/${MINA}`)).toBe(true);
  });

  it('끝의 답이 답한 말에 이벤트가 열렸으면 그 일러스트를 띄운다', async () => {
    signedIn(() => session({ messages: [message(1, 'action', { content: '[행동] 공원으로 갔다.', event_id: 'rain' }), message(2, 'assistant', { segments: [{ speaker: null, text: '비가 온다.' }] })] }));
    renderApp(`/story/sessions/${SESSION}`);

    const picture = await screen.findByRole('figure', { name: '그림 창' });
    expect(within(picture).getByRole('img', { name: '소나기' })).toBeInTheDocument();
    expect(within(picture).getByText('소나기')).toBeInTheDocument();
  });

  it('인물 창에 소개, 호감도의 단계, 고백 대기, 건넨 선물, 함께 본 이벤트를 보이고 대기 중이면 고백을 막는다', async () => {
    signedIn(() => session());
    renderApp(`/story/sessions/${SESSION}`);

    await userEvent.click(await within(await screen.findByRole('region', { name: '장면의 인물' })).findByRole('button', { name: '미나' }));
    const panel = within(screen.getByRole('dialog', { name: '미나' }));
    expect(panel.getByText('스물 · 여성')).toBeInTheDocument();
    expect(panel.getByText('호감도: 호감')).toBeInTheDocument();
    expect(panel.getByText('4일째 7시부터 다시 고백할 수 있습니다')).toBeInTheDocument();
    expect(panel.getByText('카페의 점원.')).toBeInTheDocument();
    expect(panel.getByText('건넨 선물: 꽃')).toBeInTheDocument();
    expect(panel.getByText('함께 본 이벤트: 소나기')).toBeInTheDocument();
    expect(panel.getByRole('button', { name: '고백' })).toBeDisabled();
  });

  it('내 세션 목록에 진행 한 줄을 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/worlds': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/story/conversations': () =>
        json(200, {
          items: [
            { id: SESSION, title: '여름 학교', world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' }, model: null, created_at: AT, updated_at: AT, progress: { day: 18, slot: 'evening', deadline_days: 30, ending: null, ending_name: null, epilogue: false } },
          ],
          total: 1,
        }),
    });
    renderApp('/story');
    expect(await within(await screen.findByRole('list', { name: '내 세션' })).findByText(/18일째 · D-12/)).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  it('배경, 일러스트, 그림, 호감도, 대기, 진행', () => {
    expect(backgroundOf(VIEW, { place: 'park', slot: 'evening' })).toBe(EVENING);
    expect(backgroundOf(VIEW, { place: 'park', slot: 'night' })).toBeNull();
    expect(backgroundOf(VIEW, { place: 'ghost', slot: 'evening' })).toBeNull();
    expect(sceneOf(VIEW, [], { event_id: 'rain', ending_id: null })).toEqual({ title: '소나기', imageId: RAIN });
    expect(sceneOf(VIEW, [message(1, 'user'), message(2, 'assistant')], null)).toBeNull();
    expect(portraitOf(VIEW.cast[0])).toBe(MINA);
    expect(portraitOf(undefined)).toBeNull();
    expect(stageOf(STAGES, 59)).toBe('호감');
    expect(stageOf(STAGES, 60)).toBe('사랑');
    expect(affectionText({ affection: { display: 'number', stages: [], cooling_until: null, gifts: [] } }, 45)).toBe('호감도 45');
    expect(affectionText({ affection: null }, 45)).toBeNull();
    expect(clockText(0)).toBe('1일째 0시');
    expect(coolingText({ affection: { display: 'stage', stages: [], cooling_until: 100, gifts: [] } }, 200)).toBeNull();
    expect(progressLine({ day: 3, slot: 'evening', deadline_days: null, ending: null, ending_name: null, epilogue: false })).toBe('3일째');
    expect(progressLine({ day: 9, slot: 'evening', deadline_days: 30, ending: 'spring', ending_name: '봄의 약속', epilogue: false })).toBe('끝: 봄의 약속');
    expect(progressLine({ day: 9, slot: 'evening', deadline_days: 30, ending: 'spring', ending_name: '봄의 약속', epilogue: true })).toBe('후일담 · 9일째');
    expect(progressLine(undefined)).toBeNull();
  });
});
