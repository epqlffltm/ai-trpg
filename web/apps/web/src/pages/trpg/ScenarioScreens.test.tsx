// web/apps/web/src/pages/trpg/ScenarioScreens.test.tsx
// 시나리오 탐색(B1)과 소개(B2). 로그인 전에는 토큰 없이 읽는지, 거르기와 더 보기, 이름 묻기, 소개의 고를 거리와 할 일을 본다.

import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { formatDate } from '../../format/dateTime';
import { achievementRate } from './scenario/achievementView';

const CREATOR = '00000000-0000-4000-8000-0000000000c1';
const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';

function listing(index: number, extra: Record<string, unknown> = {}) {
  return {
    scenario_id: `00000000-0000-4000-8000-${String(index).padStart(12, '0')}`,
    creator_id: CREATOR,
    title: `시나리오 ${index}`,
    tagline: `한 줄 ${index}`,
    description: '',
    genre: 'horror',
    tags: ['좀비'],
    rating: 'all',
    recommended_players: { min: 2, max: 4 },
    version: 1,
    version_note: '',
    published_at: '2026-10-20T00:00:00Z',
    ...extra,
  };
}

const DETAIL = {
  ...listing(1, { scenario_id: SCENARIO_ID, title: '잿빛 수도원', description: '종이 울리지 않는 밤.\n수도원으로 간다.' }),
  tags: ['던전 탐험'],
  openings: ['문 앞에서 시작한다.', '이미 안에 있다.'],
  character_modes: ['pregen', 'custom'],
  pregens: [{ name: '수도사 렌', description: '말이 없다', sheet: { max_hp: 12, abilities: { str: 10, wis: 15 } } }],
  abilities: [
    { key: 'str', name: '근력' },
    { key: 'wis', name: '지혜' },
  ],
  recommended_narration_model: 'gemini-flash',
  references_allowed: true,
  version_note: '보스를 고쳤다',
};

function query(request: SeenRequest): URLSearchParams {
  return new URLSearchParams(request.url.split('?')[1] ?? '');
}

const ACHIEVEMENTS = {
  players: 8,
  items: [
    { id: 'gate', hidden: false, name: '성문 앞', description: '성문에 섰다', image_id: null, earned_at: null, earned_count: 2 },
    { id: 'secret', hidden: true, name: null, description: null, image_id: null, earned_at: null, earned_count: 0 },
  ],
};

const NAMES = () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] });
// 탐색 화면의 위(Stitch 12번)는 TRPG 배너와 이번 주 인기 줄을 읽는다. 걸린 것이 없는 서버로 둔다
const SIGNED_OUT = {
  [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
  'GET /api/v1/game/banners': () => json(200, { items: [] }),
  'GET /api/v1/game/rankings/scenarios': () => json(200, { items: [] }),
};

describe('ScenarioBrowsePage', () => {
  it('로그인 전에는 토큰 없이 읽고, 장르를 화면의 말로, 만든 사람을 이름으로 보인다', async () => {
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      'GET /api/v1/game/listings': () => json(200, { items: [listing(1)], total: 1 }),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp('/trpg');

    const card = (await screen.findByText('시나리오 1')).closest('a') as HTMLElement;
    expect(within(card).getByText('호러')).toBeInTheDocument();
    expect(within(card).getByText('2~4명')).toBeInTheDocument();
    expect(await within(card).findByText('이야기꾼')).toBeInTheDocument();
    expect(card).toHaveAttribute('href', `/trpg/scenarios/${listing(1).scenario_id}`);
    const request = seen.find((entry) => entry.url.startsWith('/api/v1/game/listings')) as SeenRequest;
    expect(request.headers.has('Authorization')).toBe(false);
    expect(screen.getByText(/성인용 시나리오는 로그인하고/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument();
  });

  it('더 보기로 다음 쪽을 이어 읽고, 실패해도 읽은 것은 남긴다', async () => {
    let calls = 0;
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      'GET /api/v1/game/listings': () => {
        calls += 1;
        if (calls === 1) return json(200, { items: Array.from({ length: 20 }, (_, i) => listing(i + 1)), total: 21 });
        if (calls === 2) return json(503, { detail: '잠시' });
        return json(200, { items: [listing(21)], total: 21 });
      },
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp('/trpg');

    await userEvent.click(await screen.findByRole('button', { name: '더 보기' }));
    expect(await screen.findByText(/목록을 불러오지 못했습니다/)).toBeInTheDocument();
    expect(screen.getByText('시나리오 20')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(await screen.findByText('시나리오 21')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '더 보기' })).not.toBeInTheDocument();
    const offsets = seen.filter((entry) => entry.url.startsWith('/api/v1/game/listings')).map((entry) => query(entry).get('offset'));
    expect(offsets).toEqual(['0', '20', '20']);
  });

  it('장르를 고르면 그 조건으로 다시 읽고, 맞는 것이 없으면 조건을 푸는 길을 보인다', async () => {
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      'GET /api/v1/game/listings': (request) =>
        query(request).get('genre') ? json(200, { items: [], total: 0 }) : json(200, { items: [listing(1)], total: 1 }),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp('/trpg');

    await screen.findByText('시나리오 1');
    await userEvent.click(within(screen.getByRole('group', { name: '장르' })).getByRole('button', { name: 'SF' }));

    expect(await screen.findByText('조건에 맞는 시나리오가 없습니다.')).toBeInTheDocument();
    expect(query(seen.at(-1) as SeenRequest).get('genre')).toBe('sf');

    await userEvent.click(screen.getAllByRole('button', { name: '조건 모두 풀기' })[0] as HTMLElement);
    expect(await screen.findByText('시나리오 1')).toBeInTheDocument();
  });

  it('주소의 태그로 거르고, 태그를 풀 수 있다', async () => {
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      'GET /api/v1/game/listings': () => json(200, { items: [listing(1)], total: 1 }),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp('/trpg?tag=%EC%A2%80%EB%B9%84&players=9');

    // 태그 칩은 주소만 보고 바로 그려진다. 목록 요청이 나갔는지는 받은 결과로 기다린다.
    expect(await screen.findByText('#좀비')).toBeInTheDocument();
    expect(await screen.findByText('시나리오 1')).toBeInTheDocument();
    const first = query(seen.find((entry) => entry.url.startsWith('/api/v1/game/listings')) as SeenRequest);
    expect(first.get('tag')).toBe('좀비');
    expect(first.has('players')).toBe(false);

    await userEvent.click(screen.getByRole('button', { name: '태그 풀기' }));
    expect(screen.queryByText('#좀비')).not.toBeInTheDocument();
  });
});

describe('ScenarioPage', () => {
  it('소개글, 시작하는 장면, 프리젠을 능력치의 이름으로 보이고, 로그인 전에는 로그인하고 만들게 한다', async () => {
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, { items: [], players: 0 }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByRole('heading', { name: '잿빛 수도원', level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/수도원으로 간다/)).toBeInTheDocument();
    expect(screen.getByText('이미 안에 있다.')).toBeInTheDocument();
    expect(screen.getByText('수도사 렌')).toBeInTheDocument();
    expect(screen.getByText('지혜')).toBeInTheDocument();
    expect(screen.getByText(/준비된 캐릭터\(프리젠\), 이름과 설명만 쓰기/)).toBeInTheDocument();
    expect(screen.getByText('1판에서 바뀐 것')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '#던전 탐험' })).toHaveAttribute('href', '/trpg?tag=%EB%8D%98%EC%A0%84+%ED%83%90%ED%97%98');
    // 만든 사람을 누르면 제작자 페이지(#992)로 간다
    expect(await screen.findByRole('link', { name: '이야기꾼' })).toHaveAttribute('href', `/creators/${CREATOR}`);
    expect(screen.getByRole('link', { name: '로그인하고 테이블 만들기' })).toHaveAttribute('href', '/login');
    expect(screen.queryByText('추천 서술 모델')).not.toBeInTheDocument();
    expect(seen.some((entry) => entry.url.includes('narration-models'))).toBe(false);
  });

  it('로그인했으면 추천 모델의 이름을 보이고 테이블 만들기로 시나리오를 들고 간다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: true } }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, { items: [], players: 0 }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
      'GET /api/v1/auth/public-names': NAMES,
      'GET /api/v1/game/tables/narration-models': () =>
        json(200, { free: false, models: [{ slug: 'gemini-flash', display_name: 'Gemini Flash' }] }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByText('Gemini Flash')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '테이블 만들기' })).toHaveAttribute(
      'href',
      `/trpg/tables/new?scenario_id=${SCENARIO_ID}`,
    );
    expect(screen.getByRole('link', { name: '열린 테이블 보기' })).toHaveAttribute(
      'href',
      `/trpg/lobby?scenario_id=${SCENARIO_ID}`,
    );
  });

  it('업적을 판의 차례로 그림, 이름, 받는 법, 달성률과 함께 보인다. 숨긴 업적은 받기 전에 가린다', async () => {
    installFakeFetch({
      ...SIGNED_OUT,
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
      [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, ACHIEVEMENTS),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    const section = (await screen.findByRole('heading', { name: '업적' })).closest('section') as HTMLElement;
    const items = within(within(section).getByRole('list', { name: '업적' })).getAllByRole('listitem');
    const [gate, hidden] = items as [HTMLElement, HTMLElement];
    expect(within(gate).getByText('성문 앞')).toBeInTheDocument();
    expect(within(gate).getByText('성문에 섰다')).toBeInTheDocument();
    expect(within(gate).getByText('플레이한 8명 중 2명(25%)')).toBeInTheDocument();
    expect(within(hidden).getByText('숨긴 업적')).toBeInTheDocument();
    expect(within(hidden).getByText('받으면 이름과 받는 법이 보입니다.')).toBeInTheDocument();
    // 로그인하지 않았으면 내가 받은 수를 적지 않고 흐리게 하지 않는다
    expect(within(section).queryByText(/내가 받은 업적/)).toBeNull();
    expect(gate).not.toHaveClass('achievement-item--locked');
  });

  it('로그인했으면 내가 받은 업적은 받은 날을, 아직인 것은 흐리게 보인다', async () => {
    const mine = { ...ACHIEVEMENTS, items: [{ ...ACHIEVEMENTS.items[0], earned_at: '2026-11-09T03:00:00Z' }, ACHIEVEMENTS.items[1]] };
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: true } }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
      [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, mine),
      'GET /api/v1/auth/public-names': NAMES,
      'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    const section = (await screen.findByRole('heading', { name: '업적' })).closest('section') as HTMLElement;
    expect(within(section).getByText('내가 받은 업적 1 / 2개')).toBeInTheDocument();
    const [gate, hidden] = within(section).getAllByRole('listitem') as [HTMLElement, HTMLElement];
    expect(within(gate).getByText(`${formatDate('2026-11-09T03:00:00Z')}에 받음`)).toBeInTheDocument();
    expect(gate).not.toHaveClass('achievement-item--locked');
    expect(hidden).toHaveClass('achievement-item--locked');
  });

  it('업적이 없는 시나리오는 칸이 없다', async () => {
    const { seen } = installFakeFetch({
      ...SIGNED_OUT,
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, DETAIL),
      [`GET /api/v1/game/listings/${SCENARIO_ID}/achievements`]: () => json(200, { items: [], players: 0 }),
      'GET /api/v1/auth/public-names': NAMES,
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByRole('heading', { name: '잿빛 수도원', level: 1 })).toBeInTheDocument();
    // 업적의 답을 받고 그린 뒤에 본다
    await vi.waitFor(() => expect(seen.some((entry) => entry.url.endsWith('/achievements'))).toBe(true));
    await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
    expect(screen.queryByRole('heading', { name: '업적' })).toBeNull();
  });

  it('볼 수 없는 시나리오면 까닭을 가르지 않고 탐색으로 돌아가는 길을 둔다', async () => {
    installFakeFetch({
      ...SIGNED_OUT,
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(404, { detail: '없다' }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByText('볼 수 없는 시나리오입니다.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '다른 시나리오 찾기' })).toHaveAttribute('href', '/trpg');
  });
});

describe('achievementView', () => {
  it('달성률은 반올림한 백분율이고, 1% 보다 작으면 "1% 미만", 플레이한 사람이 없으면 그렇다고 적는다', () => {
    expect(achievementRate(2, 8)).toBe('플레이한 8명 중 2명(25%)');
    expect(achievementRate(1, 300)).toBe('플레이한 300명 중 1명(1% 미만)');
    expect(achievementRate(0, 5)).toBe('플레이한 5명 중 0명(0%)');
    expect(achievementRate(0, 0)).toBe('아직 플레이한 사람이 없습니다');
  });
});
