// web/apps/web/src/pages/me/MyCreatorStats.test.tsx
// 내 작품 숫자(#991). 펼쳐야 부르고, 서버마다 따로 부르고 따로 실패한다. 최근 7일과 모든 기간의 수, 가장 많이 쓰인 작품,
// 작품마다의 수를 보이고, 캐릭터와 세계관은 받아 온 시각(받은 적이 없으면 그 말)을 보인다. 맨 위에 내 팔로워 수를 보인다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const STATS = '/api/v1/game/me/stats/scenarios';
const SCENARIOS = {
  recent_days: 7,
  total: 1300,
  recent: 12,
  items: [
    { id: '00000000-0000-4000-8000-0000000000a1', title: '잿빛 수도원', total: 1200, recent: 10 },
    { id: '00000000-0000-4000-8000-0000000000a2', title: '안개 마을', total: 100, recent: 2 },
  ],
};
const WORLDS = {
  recent_days: 7,
  refreshed_at: '2026-11-04T03:00:00Z',
  total: 0,
  recent: 0,
  items: [{ id: '00000000-0000-4000-8000-0000000000b1', title: '여름 학교', total: 0, recent: 0 }],
};

const ME = '00000000-0000-4000-8000-0000000000c9';

/** 서명은 보지 않으므로 가운데 조각(sub)만 맞춘 토큰 */
function tokenFor(sub: string): string {
  const payload = btoa(JSON.stringify({ sub })).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `h.${payload}.s`;
}

function signedIn(routes: Record<string, () => Response>, accessToken = 'a1') {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken)),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: false } }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 0, limit: 5 }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { count: 0 }),
    ...routes,
  });
}

async function openStats() {
  renderApp('/me?tab=creator');
  await userEvent.click(await screen.findByRole('button', { name: '내 작품 숫자 보기' }));
}

describe('내 작품 숫자', () => {
  it('펼쳐야 부르고, 서버마다 수와 가장 많이 쓰인 작품을 보인다', async () => {
    const { seen } = signedIn({
      [`GET ${STATS}`]: () => json(200, SCENARIOS),
      'GET /api/v1/asset/me/stats/characters': () => json(200, { ...WORLDS, refreshed_at: null, items: [] }),
      'GET /api/v1/asset/me/stats/worlds': () => json(200, WORLDS),
    });
    renderApp('/me?tab=creator');
    await screen.findByRole('button', { name: '내 작품 숫자 보기' });
    expect(seen.some((request) => request.url.includes('/me/stats/'))).toBe(false);
    await userEvent.click(screen.getByRole('button', { name: '내 작품 숫자 보기' }));

    const scenarios = await screen.findByRole('region', { name: 'TRPG 시나리오' });
    expect(await within(scenarios).findByText('최근 7일 테이블 12회 · 모든 기간 1,300회')).toBeInTheDocument();
    expect(within(scenarios).getByText('가장 많이 쓰인 작품: 잿빛 수도원')).toBeInTheDocument();
    expect(within(scenarios).getByText('안개 마을 — 최근 7일 2회 · 모든 기간 100회')).toBeInTheDocument();
    expect(within(scenarios).queryByText(/한 시간마다/)).not.toBeInTheDocument();

    const characters = screen.getByRole('region', { name: 'chat 캐릭터' });
    expect(await within(characters).findByText('공개한 작품이 없습니다.')).toBeInTheDocument();

    // 아무도 시작하지 않았으면 가장 많이 쓰인 작품이 없다. 받아 온 시각을 보인다
    const worlds = screen.getByRole('region', { name: 'story 세계관' });
    expect(await within(worlds).findByText('최근 7일 세션 0회 · 모든 기간 0회')).toBeInTheDocument();
    expect(within(worlds).queryByText(/가장 많이 쓰인/)).not.toBeInTheDocument();
    expect(within(worlds).getByText(/수는 한 시간마다 받아 옵니다/)).toBeInTheDocument();
  });

  it('한 서버가 실패해도 다른 서버의 수는 보인다', async () => {
    signedIn({
      [`GET ${STATS}`]: () => json(503, { detail: 'down' }),
      'GET /api/v1/asset/me/stats/characters': () => json(200, { ...WORLDS, refreshed_at: null }),
      'GET /api/v1/asset/me/stats/worlds': () => json(200, WORLDS),
    });
    await openStats();

    const scenarios = await screen.findByRole('region', { name: 'TRPG 시나리오' });
    expect(await within(scenarios).findByRole('alert')).toHaveTextContent('숫자를 읽지 못했습니다');
    const characters = screen.getByRole('region', { name: 'chat 캐릭터' });
    expect(await within(characters).findByText('아직 받아 온 수가 없습니다.')).toBeInTheDocument();
  });

  it('맨 위에 내 팔로워 수를 보인다', async () => {
    signedIn(
      {
        [`GET /api/v1/notification/creators/${ME}/followers`]: () => json(200, { follower_count: 1234 }),
        [`GET ${STATS}`]: () => json(200, SCENARIOS),
        'GET /api/v1/asset/me/stats/characters': () => json(200, WORLDS),
        'GET /api/v1/asset/me/stats/worlds': () => json(200, WORLDS),
      },
      tokenFor(ME),
    );
    await openStats();

    expect(await screen.findByText('팔로워 1,234명')).toBeInTheDocument();
  });
});
