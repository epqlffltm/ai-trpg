// web/apps/web/src/pages/search/SearchPage.test.tsx
// 작품 검색(#984): 머리의 검색칸이 결과 화면으로 보내고, 결과 화면은 서버마다 검색어를 실어 따로 부르고 서비스마다 묶는다.
// 한 서버가 답하지 않으면 그 묶음만 다시 시도를 보인다. 규칙에 맞지 않는 검색어는 부르지 않는다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const SCENARIO = {
  scenario_id: 's-1',
  creator_id: 'c-1',
  title: '은하 추격전',
  tagline: '바이크로 달린다',
  description: '',
  genre: 'sf',
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
};
const WORLD = {
  id: '00000000-0000-4000-8000-00000000b801',
  version: 1,
  name: '은하 학교',
  image_id: null,
  rating: 'all',
  tags: ['학원'],
  deadline_days: 30,
  published_at: '2026-10-26T00:00:00Z',
};

async function section(title: string): Promise<HTMLElement> {
  return (await screen.findByRole('heading', { name: title })).closest('section') as HTMLElement;
}

function searched(seen: SeenRequest[], path: string): string | null {
  const request = seen.find((item) => item.url.split('?')[0] === path);
  return request ? new URL(request.url, 'http://localhost').searchParams.get('q') : null;
}

describe('SearchPage', () => {
  it('서버마다 검색어를 실어 부르고 서비스마다 묶는다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'GET /api/v1/game/listings': () => json(200, { items: [SCENARIO], total: 1 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }),
    });
    renderApp('/search?q=%EC%9D%80%ED%95%98');

    expect(await screen.findByRole('heading', { name: '"은하" 검색 결과' })).toBeInTheDocument();
    expect(await within(await section('TRPG 시나리오 1개')).findByText('은하 추격전')).toBeInTheDocument();
    expect(await within(await section('story 세계관 1개')).findByText('은하 학교')).toBeInTheDocument();
    expect(await within(await section('chat 캐릭터 0개')).findByText('찾은 캐릭터가 없습니다.')).toBeInTheDocument();
    expect(searched(seen, '/api/v1/game/listings')).toBe('은하');
    expect(searched(seen, '/api/v1/asset/listings/characters')).toBe('은하');
    expect(searched(seen, '/api/v1/asset/listings/worlds')).toBe('은하');
    expect(seen.every((request) => !request.headers.has('Authorization'))).toBe(true);
  });

  it('한 서버가 답하지 않으면 그 묶음만 다시 시도를 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'GET /api/v1/game/listings': () => json(503, { detail: 'down' }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [WORLD], total: 1 }),
    });
    renderApp('/search?q=%EC%9D%80%ED%95%98');

    expect(await within(await section('TRPG 시나리오')).findByRole('button', { name: '다시 시도' })).toBeInTheDocument();
    expect(await within(await section('story 세계관 1개')).findByText('은하 학교')).toBeInTheDocument();
  });

  it('"#" 하나뿐인 검색어는 부르지 않고 까닭을 적는다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    });
    renderApp('/search?q=%23');

    expect(await screen.findByText('# 뒤에 태그를 적어 주세요.')).toBeInTheDocument();
    expect(seen.some((request) => request.url.includes('listings'))).toBe(false);
  });

  it('머리의 검색칸이 결과 화면으로 보낸다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
      'GET /api/v1/asset/listings/worlds': () => json(200, { items: [], total: 0 }),
    });
    renderApp('/board');
    const user = userEvent.setup();

    await user.type(screen.getByRole('searchbox', { name: '작품 검색어' }), '  #학원 ');
    await user.click(screen.getByRole('button', { name: '작품 찾기' }));

    expect(await screen.findByRole('heading', { name: '"#학원" 검색 결과' })).toBeInTheDocument();
    expect(screen.getByRole('searchbox', { name: '작품 검색어' })).toHaveValue('#학원');
  });
});
