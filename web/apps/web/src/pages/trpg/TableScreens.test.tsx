// web/apps/web/src/pages/trpg/TableScreens.test.tsx
// 테이블 만들기(B4)와 로비(B3). 보내는 본문, 들어간 뒤 테이블 방(B6)이 열리는지, 비밀번호와 그 사이에 달라진 목록을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { roomRoutes } from '../../test/tableFixtures';

const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';
const TABLE_ID = '00000000-0000-4000-8000-0000000000b1';

const LISTING = {
  scenario_id: SCENARIO_ID,
  creator_id: '00000000-0000-4000-8000-0000000000c1',
  title: '잿빛 수도원',
  tagline: '',
  description: '',
  genre: 'horror',
  tags: [],
  rating: 'all',
  recommended_players: { min: 2, max: 4 },
  version: 1,
  version_note: '',
  published_at: '2026-10-20T00:00:00Z',
  openings: ['문 앞에서 시작한다.', '이미 안에 있다.'],
  character_modes: ['pregen', 'custom'],
  pregens: [],
  abilities: [],
  recommended_narration_model: 'gemini-flash',
  references_allowed: false,
};

function table(id: string, extra: Record<string, unknown> = {}) {
  return {
    id,
    scenario_id: SCENARIO_ID,
    title: `테이블 ${id.slice(-2)}`,
    status: 'recruiting',
    rating: 'all',
    capacity: 4,
    member_count: 1,
    host_id: '00000000-0000-4000-8000-0000000000c2',
    is_public: true,
    has_password: false,
    narration_style: 'classic',
    round_time_limit: 300,
    narration_model: 'gemini-flash',
    credit_wait_seconds: 300,
    remove_short_payers: true,
    whisper_notice: false,
    references_enabled: false,
    created_at: '2026-10-22T00:00:00Z',
    ...extra,
  };
}

const MODELS = {
  free: false,
  models: [
    { slug: 'gemini-flash', display_name: 'Gemini Flash', grade: 'standard', credits: '40', tier: 'standard' },
    {
      slug: 'glm-air',
      display_name: 'GLM Air',
      vendor: 'Z.ai',
      grade: 'basic',
      credits: '10',
      tier: 'basic',
      options: [
        { input_step: 0, output_step: 0, input_tokens: 12000, output_tokens: 1200, credits: '10', tier: 'basic', promo: false, next: null },
        { input_step: 1, output_step: 0, input_tokens: 20000, output_tokens: 1200, credits: '15', tier: 'basic', promo: false, next: null },
        { input_step: 1, output_step: 1, input_tokens: 20000, output_tokens: 2200, credits: '20', tier: 'basic', promo: false, next: null },
      ],
    },
  ],
};

function signedIn(routes: Record<string, (request: SeenRequest) => Response>) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', identity: { adult_content: false } }),
    'GET /api/v1/game/tables': () => json(200, { items: [], total: 0 }),
    ...roomRoutes(TABLE_ID),
    'GET /api/v1/game/tables/narration-models': () => json(200, MODELS),
    ...routes,
  });
}

function query(request: SeenRequest): URLSearchParams {
  return new URLSearchParams(request.url.split('?')[1] ?? '');
}

describe('TableCreatePage', () => {
  it('고른 것을 보내고, 만들면 테이블 방으로 간다', async () => {
    const { seen } = signedIn({
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, LISTING),
      'POST /api/v1/game/tables': () => json(201, { id: TABLE_ID }),
    });
    renderApp(`/trpg/tables/new?scenario_id=${SCENARIO_ID}`);

    await userEvent.click(await screen.findByLabelText('2번'));
    await userEvent.click(within(screen.getByRole('group', { name: '정원' })).getByRole('button', { name: '2명' }));
    await userEvent.click(screen.getByLabelText('로비에 보이기'));
    await userEvent.type(screen.getByLabelText('비밀번호(선택)'), 'abcd');
    await userEvent.click(screen.getByText('자세한 설정'));
    await userEvent.selectOptions(screen.getByLabelText('서술 모델'), 'glm-air');
    await userEvent.selectOptions(screen.getByLabelText('기억(서술에 넣는 지난 이야기)'), '1단계 · 20,000 토큰');
    await userEvent.selectOptions(screen.getByLabelText('장면의 길이'), '1단계 · 2,200 토큰');
    expect(screen.getByText(/1인 1라운드 20 크레딧/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText('준비된 캐릭터(프리젠)'));
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(seen.find((request) => request.method === 'POST' && request.url === '/api/v1/game/tables')?.body).toMatchObject({
      scenario_id: SCENARIO_ID,
      opening_index: 1,
      capacity: 2,
      is_public: true,
      password: 'abcd',
      narration_model: 'glm-air',
      input_step: 1,
      output_step: 1,
      character_modes: ['custom'],
    });
  });

  it('추천 모델을 쓸 수 없다고 하면 자세한 설정을 열고 모델 칸에 알린다', async () => {
    signedIn({
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, LISTING),
      'POST /api/v1/game/tables': () => json(422, { detail: 'narration_model 에 고를 수 없는 값이 있습니다.' }),
    });
    renderApp(`/trpg/tables/new?scenario_id=${SCENARIO_ID}`);

    await userEvent.click(await screen.findByRole('button', { name: '만들기' }));

    const model = await screen.findByLabelText('서술 모델');
    expect(model).toBeVisible();
    expect(model).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getAllByText(/서술 모델을 골라 주세요/).length).toBeGreaterThan(0);
  });

  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp(`/trpg/tables/new?scenario_id=${SCENARIO_ID}`);

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });
});

describe('LobbyPage', () => {
  it('들어가기 전에 알아야 할 설정을 보이고, 들어가면 테이블 방으로 간다', async () => {
    const { seen } = signedIn({
      'GET /api/v1/game/tables/lobby': () => json(200, { items: [table(TABLE_ID)], total: 1 }),
      [`POST /api/v1/game/tables/${TABLE_ID}/join`]: () => json(200, { id: TABLE_ID }),
    });
    renderApp('/trpg/lobby');

    const card = (await screen.findByText('테이블 b1')).closest('li') as HTMLElement;
    expect(within(card).getByText('1/4명')).toBeInTheDocument();
    expect(within(card).getByText('문체 정통')).toBeInTheDocument();
    expect(await within(card).findByText('모델 Gemini Flash')).toBeInTheDocument();

    await userEvent.click(within(card).getByRole('button', { name: '테이블 b1에 들어가기' }));

    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
    expect(seen.find((request) => request.url.endsWith('/join'))?.body).toEqual({ password: null });
  });

  it('비밀번호가 걸린 테이블은 창에서 받고, 틀리면 칸에 알린다', async () => {
    let tries = 0;
    signedIn({
      'GET /api/v1/game/tables/lobby': () => json(200, { items: [table(TABLE_ID, { has_password: true })], total: 1 }),
      [`POST /api/v1/game/tables/${TABLE_ID}/join`]: () => {
        tries += 1;
        return tries === 1 ? json(403, { detail: '비밀번호가 맞지 않습니다.' }) : json(200, { id: TABLE_ID });
      },
    });
    renderApp('/trpg/lobby');

    await userEvent.click(await screen.findByRole('button', { name: '테이블 b1에 들어가기' }));
    const dialog = screen.getByRole('dialog');
    await userEvent.type(within(dialog).getByLabelText('테이블의 비밀번호'), 'wrong');
    await userEvent.click(within(dialog).getByRole('button', { name: '들어가기' }));
    expect(await within(dialog).findByText('비밀번호가 맞지 않습니다.')).toBeInTheDocument();

    await userEvent.clear(within(dialog).getByLabelText('테이블의 비밀번호'));
    await userEvent.type(within(dialog).getByLabelText('테이블의 비밀번호'), 'right');
    await userEvent.click(within(dialog).getByRole('button', { name: '들어가기' }));
    expect(await screen.findByRole('heading', { name: '목요일 모임', level: 1 })).toBeInTheDocument();
  });

  it('그 사이에 자리가 찼으면 알리고 목록을 다시 읽는다', async () => {
    let reads = 0;
    signedIn({
      'GET /api/v1/game/tables/lobby': () => {
        reads += 1;
        return json(200, reads === 1 ? { items: [table(TABLE_ID)], total: 1 } : { items: [], total: 0 });
      },
      [`POST /api/v1/game/tables/${TABLE_ID}/join`]: () => json(409, { detail: '부딪힌다', reason: 'table_full' }),
    });
    renderApp('/trpg/lobby');

    await userEvent.click(await screen.findByRole('button', { name: '테이블 b1에 들어가기' }));

    expect(await screen.findByText('그 사이에 자리가 찼습니다.')).toBeInTheDocument();
    expect(await screen.findByText('지금 모집 중인 테이블이 없습니다.')).toBeInTheDocument();
    expect(reads).toBe(2);
  });

  it('초대 코드가 틀리면 알린다', async () => {
    const { seen } = signedIn({
      'GET /api/v1/game/tables/lobby': () => json(200, { items: [], total: 0 }),
      'POST /api/v1/game/tables/join': () => json(404, { detail: '테이블을 찾을 수 없습니다.' }),
    });
    renderApp('/trpg/lobby');

    await userEvent.type(await screen.findByLabelText('초대 코드로 들어가기'), ' ABC123 ');
    await userEvent.click(screen.getByRole('button', { name: '들어가기' }));

    expect(await screen.findByText(/초대 코드를 확인해 주세요/)).toBeInTheDocument();
    expect(seen.find((request) => request.url === '/api/v1/game/tables/join')?.body).toEqual({ invite_code: 'ABC123' });
  });

  it('시나리오로 거르면 그 제목을 보이고, 거르기를 풀 수 있다', async () => {
    const { seen } = signedIn({
      'GET /api/v1/game/tables/lobby': () => json(200, { items: [], total: 0 }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () => json(200, LISTING),
    });
    renderApp(`/trpg/lobby?scenario_id=${SCENARIO_ID}`);

    expect(await screen.findByRole('link', { name: '잿빛 수도원' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '이 시나리오로 테이블 만들기' })).toHaveAttribute(
      'href',
      `/trpg/tables/new?scenario_id=${SCENARIO_ID}`,
    );
    // 제목은 시나리오 요청의 답이다. 로비 요청이 나갔는지는 로비의 답으로 기다린다.
    expect(await screen.findByText('지금 모집 중인 테이블이 없습니다.')).toBeInTheDocument();
    const first = seen.find((request) => request.url.startsWith('/api/v1/game/tables/lobby')) as SeenRequest;
    expect(query(first).get('scenario_id')).toBe(SCENARIO_ID);

    await userEvent.click(screen.getByRole('button', { name: '모든 테이블 보기' }));
    expect(screen.queryByText(/테이블만 보고 있습니다/)).not.toBeInTheDocument();
  });
});
