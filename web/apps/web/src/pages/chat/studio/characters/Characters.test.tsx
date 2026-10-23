// web/apps/web/src/pages/chat/studio/characters/Characters.test.tsx
// 캐릭터 만들기(C6)의 뼈대. 빈 목록에서 만들기 → 고치기와 게시 점검, 점검에서 탭으로 가기, 운영자만 만드는 때(403),
// 기본과 시작 상황의 저장 본문(저장하면 점검을 다시 읽는다), 아직 화면이 없는 묶음의 문제, 숨긴 캐릭터, 게시와 걸러 낸 것,
// 지도(장소, 길, 처음 있는 장소, 지우면 길도)와 물건(시작 소지품, 그림 칸을 그대로 보내기).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';

const CHARACTERS = '/api/v1/asset/characters';
const ID = '00000000-0000-4000-8000-0000000000e1';

function character(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    name: '세라',
    age: '',
    gender: '',
    tags: [],
    rating: 'all',
    visibility: 'private',
    intro_html: '',
    greeting: '',
    speech_examples: '',
    starts: [],
    places: [],
    paths: [],
    start_place: null,
    items: [],
    start_items: [],
    affection: null,
    sprites: [],
    event_scenes: [],
    lorebooks: [],
    image_id: null,
    hidden_at: null,
    latest_version: null,
    published_at: null,
    created_at: '2026-10-24T00:00:00Z',
    updated_at: '2026-10-24T00:00:00Z',
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;

/** 로그인한 운영자와, 받은 것을 기억하는 가짜 asset 서버 */
function signedIn(initial = character(), routes: Routes = {}) {
  let current = initial;
  const check = () => {
    const problems = current.starts.length === 0 ? ['start_missing'] : [];
    return { ready: problems.length === 0, problems, removed: [] };
  };
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${CHARACTERS}`]: () => json(200, { items: [], total: 0 }),
    [`POST ${CHARACTERS}`]: (request) => {
      current = character({ name: (request.body as { name: string }).name });
      return json(201, current);
    },
    [`GET ${CHARACTERS}/${ID}`]: () => json(200, current),
    [`PATCH ${CHARACTERS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${CHARACTERS}/${ID}/publish-check`]: () => json(200, check()),
    [`GET ${CHARACTERS}/${ID}/versions`]: () => json(200, []),
    ...routes,
  });
}

function calls(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === path);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('캐릭터 만들기', () => {
  it('빈 목록에서 만들면 고치기로 가고, 점검의 문제에서 그 탭으로 간다', async () => {
    const { seen } = signedIn();
    renderApp('/chat/studio/characters');

    await userEvent.click(await screen.findByRole('link', { name: '첫 캐릭터 만들기' }));
    await userEvent.click(await screen.findByRole('button', { name: '만들기' }));
    expect(screen.getByText('이름을 적어 주세요.')).toBeInTheDocument();
    expect(calls(seen, 'POST', CHARACTERS)).toHaveLength(0);

    await userEvent.type(screen.getByLabelText('이름'), ' 세라 ');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '세라', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(calls(seen, 'POST', CHARACTERS)[0]?.body).toEqual({ name: '세라' });

    const problems = await screen.findByRole('list', { name: '고칠 것' });
    expect(within(problems).getByText('시작 상황이 하나도 없습니다.')).toBeInTheDocument();
    await userEvent.click(within(problems).getByRole('button', { name: '시작 상황 탭으로' }));
    expect(screen.getByRole('tab', { name: '시작 상황' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('form', { name: '시작 상황' })).toBeVisible();
  });

  it('운영자만 만드는 때면 알린다', async () => {
    signedIn(character(), {
      [`POST ${CHARACTERS}`]: () => json(403, { detail: '지금은 운영자만 할 수 있습니다.', code: 'operator_only' }),
    });
    renderApp('/chat/studio/characters/new');

    await userEvent.type(await screen.findByLabelText('이름'), '세라');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByText(/지금은 운영자만 캐릭터를 만들고/)).toBeInTheDocument();
  });

  it('기본 탭은 그 칸만 보내고, 저장하면 점검을 다시 읽는다', async () => {
    const { seen } = signedIn();
    renderApp(`/chat/studio/characters/${ID}`);

    const form = await screen.findByRole('form', { name: '기본' });
    await userEvent.type(within(form).getByLabelText('태그(쉼표로 나눈다)'), '기사, 판타지, 기사');
    await userEvent.type(within(form).getByLabelText('나이(선택)'), ' 스물 ');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      name: '세라',
      age: '스물',
      gender: '',
      tags: ['기사', '판타지'],
      rating: 'all',
      visibility: 'private',
    });
    await vi.waitFor(() => expect(calls(seen, 'GET', `${CHARACTERS}/${ID}/publish-check`).length).toBeGreaterThan(1));
  });

  it('시작 상황을 더해 저장하면 점검의 문제가 사라진다', async () => {
    const { seen } = signedIn();
    renderApp(`/chat/studio/characters/${ID}?tab=starts`);

    const form = await screen.findByRole('form', { name: '시작 상황' });
    await userEvent.click(within(form).getByRole('button', { name: '시작 상황 더하기' }));
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.type(within(form).getByLabelText('시작 상황 1의 제목'), '비 오는 밤');
    await userEvent.type(within(form).getByLabelText('시작 상황 1의 상황'), '문을 두드리는 소리가 난다.');
    await userEvent.clear(within(form).getByLabelText('시작 상황 1의 시각(시, 0~23)'));
    await userEvent.type(within(form).getByLabelText('시작 상황 1의 시각(시, 0~23)'), '21');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await screen.findByText('지금 게시할 수 있습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      starts: [{ title: '비 오는 밤', situation: '문을 두드리는 소리가 난다.', hour: 21 }],
    });
  });

  it('아직 화면이 없는 묶음의 문제는 이름만 적고, 숨긴 캐릭터면 알린다', async () => {
    signedIn(character({ hidden_at: '2026-10-24T01:00:00Z' }), {
      [`GET ${CHARACTERS}/${ID}/publish-check`]: () =>
        json(200, { ready: false, problems: ['affection_target_missing', 'item_missing'], removed: [] }),
    });
    renderApp(`/chat/studio/characters/${ID}`);

    expect(await screen.findByText(/운영자가 숨긴 캐릭터입니다/)).toBeInTheDocument();
    const problems = await screen.findByRole('list', { name: '고칠 것' });
    expect(within(problems).getByText('(호감도: 화면 준비 중)')).toBeInTheDocument();
    await userEvent.click(within(problems).getByRole('button', { name: '물건 탭으로' }));
    expect(screen.getByRole('form', { name: '물건' })).toBeVisible();
  });

  it('지도에 장소 둘과 길, 처음 있는 장소를 놓아 저장한다. 장소의 id 는 화면이 붙인다', async () => {
    const { seen } = signedIn();
    renderApp(`/chat/studio/characters/${ID}?tab=map`);

    const form = await screen.findByRole('form', { name: '지도' });
    expect(within(form).getByRole('button', { name: '길 더하기' })).toBeDisabled();
    await userEvent.click(within(form).getByRole('button', { name: '장소 더하기' }));
    await userEvent.click(within(form).getByRole('button', { name: '장소 더하기' }));
    await userEvent.type(within(form).getByLabelText('장소 1의 이름'), '집');
    await userEvent.type(within(form).getByLabelText('장소 2의 이름'), '시장');
    await userEvent.click(within(form).getByRole('button', { name: '길 더하기' }));
    await userEvent.selectOptions(within(form).getByLabelText('길 1의 한쪽'), '집');
    await userEvent.selectOptions(within(form).getByLabelText('길 1의 다른 쪽'), '시장');
    await userEvent.clear(within(form).getByLabelText('길 1의 시간(분)'));
    await userEvent.type(within(form).getByLabelText('길 1의 시간(분)'), '15');
    await userEvent.selectOptions(within(form).getByLabelText('처음 있는 장소'), '집');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    const body = calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body as {
      places: { id: string; name: string }[];
      paths: unknown[];
      start_place: string;
    };
    const [home, market] = body.places;
    expect(body.places.map((place) => place.name)).toEqual(['집', '시장']);
    expect(home?.id).toMatch(/^place-[0-9a-f]{8}$/);
    expect(body.paths).toEqual([{ a: home?.id, b: market?.id, minutes: 15 }]);
    expect(body.start_place).toBe(home?.id);
  });

  it('장소를 지우면 그 장소를 잇는 길도 함께 지운다고 알린다', async () => {
    const mapped = character({
      places: [
        { id: 'p1', name: '집', description: '', image_id: null, backgrounds: {} },
        { id: 'p2', name: '시장', description: '', image_id: null, backgrounds: {} },
      ],
      paths: [{ a: 'p1', b: 'p2', minutes: 10 }],
      start_place: 'p1',
    });
    signedIn(mapped);
    renderApp(`/chat/studio/characters/${ID}?tab=map`);

    const form = await screen.findByRole('form', { name: '지도' });
    expect(within(form).getAllByText('이 장소를 잇는 길 1개도 함께 지웁니다.')).toHaveLength(2);
    await userEvent.click(within(form).getByRole('button', { name: '장소 1 지우기' }));

    expect(within(form).queryByLabelText('길 1의 한쪽')).not.toBeInTheDocument();
    expect(within(form).getByLabelText('처음 있는 장소')).toHaveValue('');
  });

  it('물건과 시작 소지품을 저장한다. 물건의 그림은 그대로 보낸다', async () => {
    const image = '00000000-0000-4000-8000-0000000000f1';
    const { seen } = signedIn(
      character({ items: [{ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: image }] }),
    );
    renderApp(`/chat/studio/characters/${ID}?tab=items`);

    const form = await screen.findByRole('form', { name: '물건' });
    await userEvent.click(within(form).getByRole('button', { name: '물건 더하기' }));
    await userEvent.type(within(form).getByLabelText('물건 2의 이름'), '외투');
    await userEvent.selectOptions(within(form).getByLabelText('물건 2의 종류'), 'clothing');
    await userEvent.click(within(form).getAllByLabelText('상대가 사용자에게 줄 수 있다')[1] as HTMLElement);
    await userEvent.click(within(form).getByRole('button', { name: '시작 소지품 더하기' }));
    await userEvent.selectOptions(within(form).getByLabelText('시작 소지품 1의 물건'), '우산');
    await userEvent.clear(within(form).getByLabelText('시작 소지품 1의 수'));
    await userEvent.type(within(form).getByLabelText('시작 소지품 1의 수'), '2');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    const body = calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body as { items: Record<string, unknown>[]; start_items: unknown[] };
    expect(body.items[0]).toEqual({ id: 'i1', name: '우산', description: '', kind: 'thing', consumable: false, giftable: false, image_id: image });
    expect(body.items[1]).toMatchObject({ name: '외투', kind: 'clothing', giftable: true, consumable: false, image_id: null });
    expect(body.items[1]?.id).toMatch(/^item-[0-9a-f]{8}$/);
    expect(body.start_items).toEqual([{ item: 'i1', count: 2 }]);
  });

  it('게시하면 판을 알리고 소개에서 걸러 낸 것을 보인다. 판의 목록을 다시 읽는다', async () => {
    const ready = character({ starts: [{ title: '밤', situation: '문', hour: 21 }], intro_html: '<script>x</script>' });
    const removed = [{ kind: 'tag', name: 'script' }];
    const { seen } = signedIn(ready, {
      [`GET ${CHARACTERS}/${ID}/publish-check`]: () => json(200, { ready: true, problems: [], removed }),
      [`POST ${CHARACTERS}/${ID}/versions`]: (request) =>
        json(201, { id: 'v1', number: 1, note: (request.body as { note: string }).note, created_at: '2026-10-24T02:00:00Z', document: {}, removed }),
    });
    renderApp(`/chat/studio/characters/${ID}?tab=publish`);

    expect(await screen.findByRole('list', { name: '소개에서 걸러질 것' })).toHaveTextContent('허용하지 않는 태그: script');
    const form = screen.getByRole('form', { name: '게시' });
    await userEvent.type(within(form).getByLabelText('바뀐 것(선택)'), '첫 판');
    await userEvent.click(within(form).getByRole('button', { name: '게시' }));

    expect(await screen.findByText(/1판을 게시했습니다. 소개에서 1개를 걸러 냈습니다: 허용하지 않는 태그: script/)).toBeInTheDocument();
    expect(calls(seen, 'POST', `${CHARACTERS}/${ID}/versions`)[0]?.body).toEqual({ note: '첫 판' });
    await vi.waitFor(() => expect(calls(seen, 'GET', `${CHARACTERS}/${ID}/versions`).length).toBeGreaterThan(1));
  });

  it('마이페이지의 만들기에서 온다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () =>
        json(200, {
          public_id: 'u1',
          username: 'maker',
          email: 'm@example.com',
          nickname: '만드는 사람',
          identity: { verified: false, legal_adult: false, adult_content: false },
          guardian_consent: 'none',
          consents_pending: [],
          withdrawal_scheduled_at: null,
        }),
      'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    });
    renderApp('/me');

    expect(await screen.findByRole('link', { name: 'chat 캐릭터 만들기' })).toHaveAttribute('href', '/chat/studio/characters');
  });
});
