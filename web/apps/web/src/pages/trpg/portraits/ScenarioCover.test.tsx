// web/apps/web/src/pages/trpg/portraits/ScenarioCover.test.tsx
// 시나리오의 표지(#1164): 탐색의 카드와 소개의 머리에 공개 소개의 그림으로 받아 띄우고, 표지가 없으면 받지 않는다.
// 첫 화면의 홍보 배너는 시나리오의 표지를 그림으로 쓴다(bannerView).

import { screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { scenarioSlide } from '../../home/bannerView';

const CREATOR = '00000000-0000-4000-8000-0000000000c1';
const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';
const COVER = '00000000-0000-4000-8000-0000000000f1';
const COVER_URL = `/api/v1/game/listings/${SCENARIO_ID}/portraits/${COVER}/image`;

function listing(extra: Record<string, unknown> = {}) {
  return {
    scenario_id: SCENARIO_ID,
    creator_id: CREATOR,
    title: '잿빛 수도원',
    tagline: '종이 울리지 않는 밤',
    description: '',
    genre: 'horror',
    tags: [],
    cover_image_id: COVER,
    rating: 'all',
    recommended_players: { min: 2, max: 4 },
    version: 1,
    version_note: '',
    published_at: '2026-10-20T00:00:00Z',
    heart_count: 0,
    start_count: 0,
    ...extra,
  };
}

const DETAIL = { ...listing(), openings: ['문 앞'], character_modes: ['custom'], pregens: [], abilities: [], recommended_narration_model: null, references_allowed: false };

function signedOut(routes: Record<string, () => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    'GET /api/v1/game/banners': () => json(200, { items: [] }),
    'GET /api/v1/game/rankings/scenarios': () => json(200, { items: [] }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] }),
    [`GET ${COVER_URL}`]: () => new Response('png', { status: 200 }),
    ...routes,
  });
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:cover'), revokeObjectURL: vi.fn() });
});

describe('시나리오의 표지', () => {
  it('탐색의 카드 맨 위에 표지를 띄운다', async () => {
    signedOut({ 'GET /api/v1/game/listings': () => json(200, { items: [listing()], total: 1 }) });
    renderApp('/trpg');

    const card = (await screen.findByText('잿빛 수도원')).closest('a') as HTMLElement;
    await vi.waitFor(() => expect(card.querySelector('img.item-card__image')).toHaveAttribute('src', 'blob:cover'));
  });

  it('소개의 머리에 표지를 두고, 표지가 없으면 그림을 받지 않는다', async () => {
    const { seen } = signedOut({ [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL) });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    const head = (await screen.findByRole('heading', { level: 1, name: '잿빛 수도원' })).closest('header') as HTMLElement;
    await vi.waitFor(() => expect(head.querySelector('img.scenario__cover')).toHaveAttribute('src', 'blob:cover'));
    expect(seen.filter((request) => request.url === COVER_URL)).toHaveLength(1);
    expect(within(head).getByText('종이 울리지 않는 밤')).toBeInTheDocument();
  });

  it('홍보 배너의 시나리오는 표지를 그림으로 쓴다. 표지가 없으면 그림 없이다', () => {
    const banner = { id: 'b1', listing: listing() } as never;
    expect(scenarioSlide(banner).scenarioCover).toEqual({ scenarioId: SCENARIO_ID, imageId: COVER });
    expect(scenarioSlide({ id: 'b2', listing: listing({ cover_image_id: null }) } as never).scenarioCover).toBeNull();
  });
});
