// web/apps/web/src/pages/me/achievements/MyWorkAchievements.test.tsx
// 마이페이지 설정 탭의 "작품 업적"(#193). 처음에는 TRPG 의 것을 받은 때가 늦은 것부터 보이고, 서비스 칩을 누르면 그 서버의 것만 읽는다.
// 줄마다 그림, 이름, 받는 법, 작품의 이름(소개로 가는 길), 받은 날. 더 보기로 이어 읽는다. 받은 것이 없으면 그렇다고,
// 읽지 못하면 다시 시도를 둔다. TRPG 는 공개를 내린 시나리오면 길과 그림이 없고, 판에서 뺀 업적은 이름이 없다. 줄을 짓는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { chatLine, MISSING_ACHIEVEMENT, MISSING_WORK, nextAchievementOffset, scenarioLine, storyLine, totalLine } from './myAchievementsView';

const SCENARIO = '00000000-0000-4000-8000-00000000a701';
const GONE = '00000000-0000-4000-8000-00000000a702';
const WORLD = '00000000-0000-4000-8000-00000000a703';
const CHARACTER = '00000000-0000-4000-8000-00000000a704';
const PICTURE = '00000000-0000-4000-8000-00000000a705';
const AT = '2026-11-09T03:00:00Z';
const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: true, legal_adult: true, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
};

function scenarioItem(achievementId: string, extra: Record<string, unknown> = {}) {
  return {
    scenario_id: SCENARIO,
    scenario_title: '성의 모험',
    listed: true,
    achievement_id: achievementId,
    name: `${achievementId} 업적`,
    description: `${achievementId} 을 했다`,
    image_id: null,
    earned_at: AT,
    ...extra,
  };
}

const STORY_ITEM = { world_id: WORLD, world_name: '바닷가 마을', achievement_id: 'beach', name: '해변의 하루', description: '', image_id: null, earned_at: AT, conversation_id: null };
const CHAT_ITEM = { character_id: CHARACTER, character_name: null, achievement_id: 'chatty', name: '수다쟁이', description: '많이 이야기했다', image_id: PICTURE, earned_at: AT, conversation_id: null };

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedIn(routes: Routes = {}) {
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:achievement'), revokeObjectURL: vi.fn() });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/auth/me/badges': () => json(200, { earned: 0, badges: [] }),
    'GET /api/v1/auth/me/blocks': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/auth/me/following': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/auth/me/invites': () => json(200, { code: null, invited: 0 }),
    'GET /api/v1/game/achievements/mine': (request) => {
      const offset = new URL(request.url, 'http://x').searchParams.get('offset');
      if (offset === '20') return json(200, { items: [scenarioItem('last')], total: 21 });
      const items = [
        scenarioItem('first', { image_id: PICTURE }),
        scenarioItem('removed', { name: null, description: null }),
        scenarioItem('hidden', { scenario_id: GONE, scenario_title: '내린 시나리오', listed: false, image_id: PICTURE }),
        ...Array.from({ length: 17 }, (_, index) => scenarioItem(`more-${index}`)),
      ];
      return json(200, { items, total: 21 });
    },
    'GET /api/v1/story/achievements/mine': () => json(200, { items: [STORY_ITEM], total: 1 }),
    'GET /api/v1/chat/achievements/mine': () => json(200, { items: [CHAT_ITEM], total: 1 }),
    [`GET /api/v1/asset/images/${PICTURE}`]: () => new Response('png', { status: 200 }),
    [`GET /api/v1/game/listings/${SCENARIO}/portraits/${PICTURE}/image`]: () => new Response('png', { status: 200 }),
    ...routes,
  });
}

async function section() {
  return within(await screen.findByRole('region', { name: '작품 업적' }));
}

const asked = (seen: SeenRequest[], prefix: string) => seen.filter((request) => request.url.startsWith(prefix));

afterEach(() => {
  vi.restoreAllMocks();
});

describe('마이페이지의 작품 업적', () => {
  it('TRPG 의 것을 늦은 것부터 보이고 더 보기로 이어 읽는다. 다른 서버는 부르지 않는다', async () => {
    const { seen } = signedIn();
    renderApp('/me?tab=settings');

    const panel = await section();
    expect(panel.getByRole('button', { name: 'TRPG' })).toHaveAttribute('aria-pressed', 'true');
    const list = within(await panel.findByRole('list', { name: '받은 작품 업적' }));
    expect(panel.getByText('TRPG에서 받은 업적 21개')).toBeInTheDocument();
    expect(list.getByText('first 업적')).toBeInTheDocument();
    expect(list.getByText('first 을 했다')).toBeInTheDocument();
    expect(list.getAllByRole('link', { name: '성의 모험' })[0]).toHaveAttribute('href', `/trpg/scenarios/${SCENARIO}`);
    // 판에서 뺀 업적은 이름이 없다. 공개를 내린 시나리오는 길이 없다
    expect(list.getByText(MISSING_ACHIEVEMENT)).toBeInTheDocument();
    expect(list.getByText('내린 시나리오').closest('a')).toBeNull();
    expect(list.getAllByRole('listitem')).toHaveLength(20);

    await userEvent.click(panel.getByRole('button', { name: '더 보기' }));
    expect(await list.findByText('last 업적')).toBeInTheDocument();
    expect(panel.queryByRole('button', { name: '더 보기' })).toBeNull();
    expect(asked(seen, '/api/v1/game/achievements/mine').map((request) => new URL(request.url, 'http://x').searchParams.get('offset'))).toEqual(['0', '20']);
    expect(asked(seen, '/api/v1/story/achievements/mine')).toHaveLength(0);
    expect(asked(seen, '/api/v1/chat/achievements/mine')).toHaveLength(0);
    // 그림은 공개된 시나리오의 주소로 받는다. 공개를 내린 시나리오의 그림은 받지 않는다
    expect(await list.findByRole('img', { name: 'first 업적의 그림' })).toHaveAttribute('src', 'blob:achievement');
    expect(asked(seen, '/api/v1/game/listings/').map((request) => request.url)).toEqual([`/api/v1/game/listings/${SCENARIO}/portraits/${PICTURE}/image`]);
    expect(asked(seen, '/api/v1/asset/images/')).toHaveLength(0);
  });

  it('스토리와 채팅을 고르면 그 서버의 것을 읽는다. 채팅의 그림은 그림 저장소에서 받는다', async () => {
    signedIn();
    renderApp('/me?tab=settings');

    const panel = await section();
    await userEvent.click(panel.getByRole('button', { name: '스토리' }));
    const stories = within(await panel.findByRole('list', { name: '받은 작품 업적' }));
    expect(await stories.findByText('해변의 하루')).toBeInTheDocument();
    expect(stories.getByRole('link', { name: '바닷가 마을' })).toHaveAttribute('href', `/story/worlds/${WORLD}`);
    expect(panel.getByText('스토리에서 받은 업적 1개')).toBeInTheDocument();

    await userEvent.click(panel.getByRole('button', { name: '채팅' }));
    expect(await panel.findByText('수다쟁이')).toBeInTheDocument();
    const chats = within(panel.getByRole('list', { name: '받은 작품 업적' }));
    expect(chats.getByRole('link', { name: MISSING_WORK })).toHaveAttribute('href', `/chat/characters/${CHARACTER}`);
    expect(await chats.findByRole('img', { name: '수다쟁이의 그림' })).toHaveAttribute('src', 'blob:achievement');
    // 고른 칩을 다시 눌러도 고른 것이 그대로다
    await userEvent.click(panel.getByRole('button', { name: '채팅' }));
    expect(panel.getByRole('button', { name: '채팅' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('받은 것이 없으면 그렇다고, 읽지 못하면 다시 시도한다', async () => {
    let fail = true;
    signedIn({
      'GET /api/v1/game/achievements/mine': () => (fail ? json(503, { detail: 'down' }) : json(200, { items: [], total: 0 })),
    });
    renderApp('/me?tab=settings');

    const panel = await section();
    const retry = await panel.findByRole('button', { name: '다시 시도' }, { timeout: 5000 });
    expect(panel.getByText(/작품 업적을 불러오지 못했습니다/)).toBeInTheDocument();
    fail = false;
    await userEvent.click(retry);
    expect(await panel.findByText('아직 받은 업적이 없습니다.')).toBeInTheDocument();
  });

  it('다른 탭에서는 부르지 않는다', async () => {
    const { seen } = signedIn({ 'GET /api/v1/auth/me/consents': () => json(200, { items: [] }) });
    renderApp('/me');

    expect(await screen.findByRole('heading', { name: '모험가' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '작품 업적' })).toBeNull();
    expect(asked(seen, '/api/v1/game/achievements/mine')).toHaveLength(0);
  });
});

describe('작품 업적의 줄', () => {
  it('세 서버의 것을 한 모양으로 바꾼다', () => {
    expect(scenarioLine(scenarioItem('a', { image_id: PICTURE }))).toEqual({
      key: `${SCENARIO}/a`,
      name: 'a 업적',
      description: 'a 을 했다',
      workName: '성의 모험',
      workLink: `/trpg/scenarios/${SCENARIO}`,
      image: { kind: 'listing', scenarioId: SCENARIO, imageId: PICTURE },
      earnedAt: AT,
    });
    expect(scenarioLine(scenarioItem('a', { listed: false, image_id: PICTURE }))).toMatchObject({ workLink: null, image: null });
    expect(scenarioLine(scenarioItem('a', { name: null, description: null }))).toMatchObject({ name: MISSING_ACHIEVEMENT, description: '' });
    expect(storyLine({ ...STORY_ITEM, world_name: null, image_id: PICTURE })).toMatchObject({ workName: MISSING_WORK, image: { kind: 'asset', imageId: PICTURE }, key: `${WORLD}/beach` });
    expect(storyLine(STORY_ITEM).image).toBeNull();
    expect(chatLine({ ...CHAT_ITEM, character_name: '루나', image_id: null })).toMatchObject({ workName: '루나', workLink: `/chat/characters/${CHARACTER}`, image: null });
    expect(totalLine('chat', 3)).toBe('채팅에서 받은 업적 3개');
    expect([nextAchievementOffset(20, 21), nextAchievementOffset(20, 20)]).toEqual([20, undefined]);
  });
});
