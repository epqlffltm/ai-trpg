// web/apps/web/src/pages/creator/Creator.test.tsx
// 제작자(#992). 제작자 페이지가 프로필과 서비스마다의 공개 작품을 서버마다 따로 부르는지(만든 사람의 공개 ID 를 싣는다),
// 없거나 탈퇴한 제작자의 안내, 한 서버가 답하지 않을 때, 마이페이지에서 소개를 고치는 것을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const CREATOR = '0b6f1d2e-0000-4000-8000-0000000000c1';
const PROFILE = { public_id: CREATOR, nickname: '이야기꾼', bio: '밤의 이야기를 씁니다' };
const SCENARIO = {
  scenario_id: 's-1',
  creator_id: CREATOR,
  title: '잿빛 수도원',
  tagline: '종이 울리지 않는 밤',
  description: '',
  genre: 'horror',
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
};
const WORLD = {
  id: '00000000-0000-4000-8000-00000000b801',
  creator_id: CREATOR,
  version: 1,
  name: '은하 학교',
  image_id: null,
  rating: 'all',
  tags: ['학원'],
  deadline_days: 30,
  published_at: '2026-10-26T00:00:00Z',
};
const PATH = `/creators/${CREATOR}`;

async function section(title: string): Promise<HTMLElement> {
  return (await screen.findByRole('heading', { name: title })).closest('section') as HTMLElement;
}

function creatorOf(seen: SeenRequest[], path: string): string | null {
  const request = seen.find((item) => item.url.split('?')[0] === path);
  return request ? new URL(request.url, 'http://localhost').searchParams.get('creator') : null;
}

describe('제작자 페이지', () => {
  it('프로필과 서비스마다의 공개 작품을 서버마다 따로 부른다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET /api/v1/auth/creators/${CREATOR}`]: () => json(200, PROFILE),
      'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }),
    });
    renderApp(PATH);

    expect(await screen.findByRole('heading', { level: 1, name: '이야기꾼' })).toBeInTheDocument();
    expect(screen.getByText('밤의 이야기를 씁니다')).toBeInTheDocument();
    expect(await within(await section('TRPG 시나리오 1개')).findByText('잿빛 수도원')).toBeInTheDocument();
    expect(await within(await section('story 세계관 1개')).findByText('은하 학교')).toBeInTheDocument();
    expect(await within(await section('chat 캐릭터 0개')).findByText('공개한 캐릭터가 없습니다.')).toBeInTheDocument();
    expect(creatorOf(seen, '/api/v1/game/listings')).toBe(CREATOR);
    expect(creatorOf(seen, '/api/v1/asset/listings/characters')).toBe(CREATOR);
    expect(creatorOf(seen, '/api/v1/asset/listings/worlds')).toBe(CREATOR);
  });

  it('한 서버가 답하지 않으면 그 묶음만 다시 시도를 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET /api/v1/auth/creators/${CREATOR}`]: () => json(200, PROFILE),
      'GET /api/v1/game/listings': () => json(503, { detail: 'down' }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }),
    });
    renderApp(PATH);

    expect(await within(await section('TRPG 시나리오')).findByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(await within(await section('story 세계관 1개')).findByText('은하 학교')).toBeInTheDocument();
  });

  it('없거나 탈퇴한 제작자면 그 안내만 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET /api/v1/auth/creators/${CREATOR}`]: () => json(404, { detail: 'x', code: 'creator_not_found' }),
      'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [], total: 0 }),
    });
    renderApp(PATH);

    expect(await screen.findByText('없거나 탈퇴한 제작자입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: /TRPG 시나리오/ })).not.toBeInTheDocument();
  });
});

describe('제작자 소개', () => {
  it('마이페이지에서 소개를 고쳐 저장한다', async () => {
    const me = {
      public_id: CREATOR,
      username: 'maker',
      email: 'maker@example.com',
      nickname: '이야기꾼',
      identity: { verified: false, legal_adult: false, adult_content: false },
      guardian_consent: 'none',
      consents_pending: [],
      withdrawal_scheduled_at: null,
      bio: '',
    };
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, me),
      'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
      'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 0, limit: 5 }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { count: 0 }),
      'PATCH /api/v1/auth/me/profile': (request) => json(200, { bio: String((request.body as { bio: string }).bio).trim() }),
    });
    renderApp('/me');

    const form = await section('제작자 소개');
    expect(within(form).getByRole('link', { name: '내 제작자 페이지' })).toHaveAttribute('href', PATH);
    await userEvent.type(within(form).getByRole('textbox', { name: '소개' }), ' 밤의 이야기를 씁니다 ');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByRole('status')).toHaveTextContent('저장했습니다.');
    expect(seen.find((request) => request.method === 'PATCH')?.body).toEqual({ bio: ' 밤의 이야기를 씁니다 ' });
    expect(within(form).getByRole('textbox', { name: '소개' })).toHaveValue('밤의 이야기를 씁니다');
    expect(within(form).getByText('11/200자. 비우면 소개가 없습니다.')).toBeInTheDocument();
  });
});
