// web/apps/web/src/pages/story/StoryStage.test.tsx
// 그림 창의 무대(D2, Stitch 22번). 배경이 있으면 장면의 인물 줄을 배경 위에 겹치고, 말하는 인물만 밝힌다(data-speaking).
// 그림이 늦게 와도 인물 줄이 새로 그려지지 않아 열어 둔 인물 창이 닫히지 않는다. 일러스트가 열리면 인물 줄은 그림 아래다.
// 열린 이벤트의 선택지는 그림 위에 겹친다(무대면 그림 창에, 일러스트면 일러스트의 틀에). 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import type { StoryMessage, StorySession, StoryState } from '../../api/story';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { castOut, storyView } from '../../test/storyFixtures';
import { speakingOf } from './storyCastView';
import { pictureMode } from '../../components/stage/StagePicture';

const SESSION = '00000000-0000-4000-8000-00000000ad21';
const WORLD = '00000000-0000-4000-8000-00000000bd21';
const PARK = '00000000-0000-4000-8000-0000000000e1';
const RAIN = '00000000-0000-4000-8000-0000000000e2';
const M = (n: number) => `00000000-0000-4000-8000-0000000fe2${n}`;
const AT = '2026-10-27T03:00:00Z';

const VIEW = storyView({
  slots: [{ id: 'evening', name: '저녁', start_hour: 18 }],
  places: [{ id: 'park', name: '공원', description: '', image_id: PARK, backgrounds: {} }],
  events: [{ id: 'rain', name: '소나기', image_id: RAIN, cast: [], choices: [{ id: 'share', text: '우산을 함께 쓴다' }, { id: 'run', text: '뛰어간다' }] }] as never,
  cast: [castOut('mina', '미나'), castOut('jun', '준')],
});

function state(choosing: string | null = null): StoryState {
  return { minutes: 18 * 60, day: 1, slot: 'evening', place: 'park', items: {}, affection: {}, companions: [], choosing, ending: null, cast: ['mina', 'jun'] };
}

function message(n: number, role: string, extra: Partial<StoryMessage> = {}): StoryMessage {
  return { id: M(n), parent_id: n === 1 ? null : M(n - 1), role, content: '', status: 'complete', segments: [], cast: [], created_at: AT, edited: false, alternatives: [M(n)], ...extra };
}

function session(messages: StoryMessage[], choosing: string | null = null): StorySession {
  return {
    id: SESSION,
    title: '여름 학교',
    world: { id: WORLD, version: 1, name: '여름 학교', image_id: null, rating: 'all' },
    view: VIEW,
    model: { slug: 'luna', display_name: 'Luna', vendor: 'openai', grade: 'standard', retires_on: null, usable: true },
    messages,
    state: state(choosing),
    created_at: AT,
    updated_at: AT,
  } as StorySession;
}

const TALK = [
  message(1, 'user', { content: '안녕?' }),
  message(2, 'assistant', {
    segments: [
      { speaker: 'jun', expression: null, text: '늦었잖아.' },
      { speaker: 'mina', expression: null, text: '안녕!' },
      { speaker: null, expression: null, text: '바람이 분다.' },
    ],
  }),
];

/** 그림은 늦게 온다(release 를 부를 때까지). 인물 줄이 다시 그려지는지 보려고 */
function signedIn(messages: StoryMessage[], choosing: string | null = null) {
  let release: () => void = () => undefined;
  const late = new Promise<void>((resolve) => {
    release = resolve;
  });
  const image = async () => {
    await late;
    return new Response('png', { status: 200 });
  };
  installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET /api/v1/story/conversations/${SESSION}`]: () => json(200, session(messages, choosing)),
    [`GET /api/v1/asset/images/${PARK}`]: image,
    [`GET /api/v1/asset/images/${RAIN}`]: image,
  });
  return { release: () => release() };
}

beforeEach(() => {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:image'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('그림 창의 무대', () => {
  it('배경 위에 장면의 인물을 겹치고 말하는 인물만 밝힌다. 그림이 늦게 와도 열어 둔 인물 창은 닫히지 않는다', async () => {
    const images = signedIn(TALK);
    renderApp(`/story/sessions/${SESSION}`);

    const cast = within(await screen.findByRole('region', { name: '장면의 인물' }));
    await userEvent.click(cast.getByRole('button', { name: '미나' }));
    expect(screen.getByRole('dialog', { name: '미나' })).toBeInTheDocument();

    images.release();
    const picture = await screen.findByRole('figure', { name: '그림 창' });
    expect(within(picture).getByRole('region', { name: '장면의 인물' })).toBeInTheDocument();
    expect(screen.getByRole('dialog', { name: '미나' })).toBeInTheDocument();
    expect(cast.getByRole('button', { name: '미나' })).toHaveAttribute('data-speaking', 'true');
    expect(cast.getByRole('button', { name: '준' })).toHaveAttribute('data-speaking', 'false');
  });

  it('이벤트의 일러스트가 열리면 장면의 인물 줄은 그림 아래에 둔다', async () => {
    const images = signedIn([message(1, 'action', { content: '[행동] 공원으로 갔다.', event_id: 'rain' }), message(2, 'assistant', { segments: [{ speaker: null, text: '비가 온다.' }] })]);
    renderApp(`/story/sessions/${SESSION}`);

    images.release();
    const picture = await screen.findByRole('figure', { name: '그림 창' });
    expect(within(picture).getByRole('img', { name: '소나기' })).toBeInTheDocument();
    expect(picture).toHaveClass('stage-picture--scene');
    expect(screen.getByRole('button', { name: '미나' })).not.toHaveAttribute('data-speaking');
  });
});

describe('그림 위의 선택지', () => {
  it('무대면 그림 창 위에 선택지를 겹치고, 번호는 단추의 이름에 들지 않는다', async () => {
    const images = signedIn(TALK, 'rain');
    renderApp(`/story/sessions/${SESSION}`);

    images.release();
    const picture = await screen.findByRole('figure', { name: '그림 창' });
    const choices = within(within(picture).getByRole('region', { name: '선택지' }));
    expect(choices.getByText('소나기')).toBeInTheDocument();
    const share = choices.getByRole('button', { name: '우산을 함께 쓴다' });
    expect(share.querySelector('.story-choice__number')).toHaveTextContent('1');
    expect(share.closest('.stage-picture__overlay')).not.toBeNull();
  });

  it('일러스트가 열려 있으면 일러스트의 틀 안에 겹친다', async () => {
    const images = signedIn([message(1, 'action', { content: '[행동] 공원으로 갔다.', event_id: 'rain' }), message(2, 'assistant', { segments: [{ speaker: null, text: '비가 온다.' }] })], 'rain');
    renderApp(`/story/sessions/${SESSION}`);

    images.release();
    const picture = await screen.findByRole('figure', { name: '그림 창' });
    const region = within(picture).getByRole('region', { name: '선택지' });
    expect(region.closest('.stage-picture__frame')).not.toBeNull();
  });
});

describe('순수한 함수', () => {
  it('그림 창의 모드와 지금 말하는 인물', () => {
    expect(pictureMode(false, false)).toBe('none');
    expect(pictureMode(false, true)).toBe('none');
    expect(pictureMode(true, false)).toBe('stage');
    expect(pictureMode(true, true)).toBe('scene');
    // chat 처럼 늘 무대를 두면(framed) 배경이 없어도 무대다. 컷신은 그림이 와야 컷신이다
    expect(pictureMode(false, false, true)).toBe('stage');
    expect(pictureMode(false, true, true)).toBe('stage');
    expect(speakingOf([{ speaker: 'jun' }, { speaker: 'mina' }, { speaker: null }])).toBe('mina');
    expect(speakingOf([{ speaker: null }])).toBeNull();
    expect(speakingOf([])).toBeNull();
  });
});
