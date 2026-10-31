// web/apps/web/src/pages/chat/studio/characters/Characters.test.tsx
// 캐릭터 만들기(C6)의 뼈대. 빈 목록에서 만들기 → 고치기와 게시 점검, 점검에서 탭으로 가기, 운영자만 만드는 때(403),
// 기본과 시작 상황의 저장 본문(저장하면 점검을 다시 읽는다), 모르는 문제, 숨긴 캐릭터, 게시와 걸러 낸 것,
// 지도(장소, 길, 처음 있는 장소, 지우면 길도)와 물건(시작 소지품, 그림 칸을 그대로 보내기),
// 호감도(켜고 끄기, 단계, 규칙의 대상과 화면이 붙이는 id), 그림(올리기, 토큰을 실은 미리 보기, 장소의 배경, 막힌 올리기),
// 캐릭터 그림(체크무늬 미리 보기, 옷만 고르는 차림), 이벤트 씬(조건을 바꾸면 대상을 비우기, 호감도 단계),
// 로어북(고르기 목록에서 붙이기, 차례, 게시하지 않은 것과 목록에 없는 것, 남의 로어북의 422).

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
    genre: 'romance',
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
    // 로어북 탭의 고르기 목록. 탭은 모두 그려 두므로 어느 탭에서든 읽는다
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
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
    // 장르는 반드시 하나를 고른다. 고르지 않으면 만들지 않는다
    expect(screen.getByText('장르를 골라 주세요.')).toBeInTheDocument();
    expect(calls(seen, 'POST', CHARACTERS)).toHaveLength(0);

    await userEvent.type(screen.getByLabelText('이름'), ' 세라 ');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));
    expect(calls(seen, 'POST', CHARACTERS)).toHaveLength(0);
    await userEvent.selectOptions(screen.getByLabelText('장르'), '로맨스');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByRole('heading', { name: '세라', level: 1 })).toBeInTheDocument();
    expect(screen.getByText('만들었습니다.')).toBeInTheDocument();
    expect(calls(seen, 'POST', CHARACTERS)[0]?.body).toEqual({ name: '세라', genre: 'romance' });

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
    await userEvent.selectOptions(screen.getByLabelText('장르'), '판타지');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByText(/지금은 운영자만 캐릭터를 만들고/)).toBeInTheDocument();
  });

  it('기본 탭은 그 칸만 보내고, 저장하면 점검을 다시 읽는다', async () => {
    const { seen } = signedIn();
    renderApp(`/chat/studio/characters/${ID}`);

    const form = await screen.findByRole('form', { name: '기본' });
    await userEvent.type(within(form).getByLabelText('태그(쉼표로 나눈다)'), '기사, 판타지, 기사');
    await userEvent.type(within(form).getByLabelText('나이(선택)'), ' 스물 ');
    // 장르는 하나를 고른다. 남성향·여성향은 장르에 없다(태그)
    expect(within(form).queryByRole('option', { name: '남성향' })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText('장르'), '무협');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      name: '세라',
      age: '스물',
      gender: '',
      genre: 'wuxia',
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

  it('모르는 문제는 이름만 적고, 숨긴 캐릭터면 알린다', async () => {
    signedIn(character({ hidden_at: '2026-10-24T01:00:00Z' }), {
      [`GET ${CHARACTERS}/${ID}/publish-check`]: () => json(200, { ready: false, problems: ['new_problem', 'item_missing'], removed: [] }),
    });
    renderApp(`/chat/studio/characters/${ID}`);

    expect(await screen.findByText(/운영자가 숨긴 캐릭터입니다/)).toBeInTheDocument();
    const problems = await screen.findByRole('list', { name: '고칠 것' });
    expect(within(problems).getByText('new_problem')).toBeInTheDocument();
    expect(within(problems).getAllByRole('button')).toHaveLength(1);
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

  it('호감도를 켜고 단계와 규칙을 더해 저장한다. 규칙의 대상은 저장한 물건에서 고른다', async () => {
    const { seen } = signedIn(
      character({ items: [{ id: 'i1', name: '꽃', description: '', kind: 'thing', consumable: false, giftable: false, image_id: null }] }),
    );
    renderApp(`/chat/studio/characters/${ID}?tab=affection`);

    const form = await screen.findByRole('form', { name: '호감도' });
    expect(within(form).queryByLabelText('보이는 방식')).not.toBeInTheDocument();
    await userEvent.click(within(form).getByLabelText('호감도를 쓴다'));
    await userEvent.click(within(form).getByRole('button', { name: '단계 더하기' }));
    await userEvent.type(within(form).getByLabelText('단계 2의 이름'), '친구');
    await userEvent.click(within(form).getByRole('button', { name: '규칙 더하기' }));
    await userEvent.selectOptions(within(form).getByLabelText('규칙 1의 대상'), '꽃');
    await userEvent.click(within(form).getByLabelText('처음 한 번만'));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    const body = calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body as { affection: { rules: { id: string }[] } };
    expect(body.affection).toEqual({
      display: 'number',
      start: 0,
      model_step: 3,
      stages: [
        { name: '처음', at: 0 },
        { name: '친구', at: 10 },
      ],
      rules: [{ id: expect.stringMatching(/^rule-[0-9a-f]{8}$/), on: { kind: 'give_item', target: 'i1' }, change: 5, once: true }],
    });
  });

  it('호감도를 끄면 null 로 보내고, 장소의 규칙은 장소에서 고른다', async () => {
    const affection = {
      display: 'stage',
      start: 10,
      model_step: 0,
      stages: [{ name: '처음', at: 0 }],
      rules: [{ id: 'rule-1', on: { kind: 'give_item', target: 'i1' }, change: 3, once: false }],
    };
    const { seen } = signedIn(
      character({ affection, places: [{ id: 'p1', name: '바다', description: '', image_id: null, backgrounds: {} }] }),
    );
    renderApp(`/chat/studio/characters/${ID}?tab=affection`);

    const form = await screen.findByRole('form', { name: '호감도' });
    await userEvent.selectOptions(within(form).getByLabelText('규칙 1의 행동'), 'reach_place');
    expect(within(form).getByLabelText('규칙 1의 대상')).toHaveValue('');
    expect(within(form).getByRole('option', { name: '바다' })).toBeInTheDocument();
    await userEvent.click(within(form).getByLabelText('호감도를 쓴다'));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({ affection: null });
  });

  it('그림 탭에서 대표 그림과 장소의 밤 배경을 올려 붙인다. 미리 보기는 토큰을 실어 받은 blob 이다', async () => {
    // jsdom 에는 blob: 주소를 만드는 함수가 없다
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:preview'), revokeObjectURL: vi.fn() });
    const ids = ['00000000-0000-4000-8000-00000000a001', '00000000-0000-4000-8000-00000000a002'];
    const home = { id: 'p1', name: '집', description: '', image_id: null, backgrounds: {} };
    const { seen } = signedIn(character({ places: [home] }), {
      'POST /api/v1/asset/images': () => json(201, { id: ids.shift(), format: 'png', byte_size: 3, width: 1, height: 1, url: '', created_at: '' }),
      [`GET /api/v1/asset/images/00000000-0000-4000-8000-00000000a001`]: () => new Response('png', { status: 200 }),
      [`GET /api/v1/asset/images/00000000-0000-4000-8000-00000000a002`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/chat/studio/characters/${ID}?tab=images`);

    const form = await screen.findByRole('form', { name: '그림' });
    const file = new File(['png'], 'face.png', { type: 'image/png' });
    await userEvent.upload(within(form).getByLabelText('대표 그림'), file);
    expect(await within(form).findByRole('img', { name: '대표 그림' })).toHaveAttribute('src', 'blob:preview');
    const upload = calls(seen, 'POST', '/api/v1/asset/images')[0];
    expect(upload?.body).toBe(file);
    expect(upload?.headers.get('Content-Type')).toBe('image/png');

    await userEvent.click(within(form).getByText('집'));
    await userEvent.upload(within(form).getByLabelText('집의 밤 배경'), file);
    await within(form).findByRole('img', { name: '집의 밤 배경' });
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      image_id: '00000000-0000-4000-8000-00000000a001',
      places: [{ ...home, backgrounds: { night: '00000000-0000-4000-8000-00000000a002' } }],
      items: [],
    });
    const preview = calls(seen, 'GET', '/api/v1/asset/images/00000000-0000-4000-8000-00000000a001')[0];
    expect(preview?.headers.get('Authorization')).toBe('Bearer a1');
  });

  it('올리기가 막히면 알린다', async () => {
    signedIn(character(), {
      'POST /api/v1/asset/images': () => json(415, { detail: 'PNG, JPEG, WebP 그림만 올릴 수 있습니다.', code: 'image_format' }),
    });
    renderApp(`/chat/studio/characters/${ID}?tab=images`);

    const form = await screen.findByRole('form', { name: '그림' });
    await userEvent.upload(within(form).getByLabelText('대표 그림'), new File(['x'], 'a.png', { type: 'image/png' }));

    expect(await within(form).findByText('PNG, JPEG, WebP 그림만 올릴 수 있습니다.')).toBeInTheDocument();
  });

  it('캐릭터 그림을 올리고 표정과 옷을 골라 저장한다. 미리 보기는 체크무늬 위다', async () => {
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:sprite'), revokeObjectURL: vi.fn() });
    const sprite = '00000000-0000-4000-8000-00000000b001';
    const coat = { id: 'coat', name: '외투', description: '', kind: 'clothing', consumable: false, giftable: false, image_id: null };
    const flower = { ...coat, id: 'flower', name: '꽃', kind: 'thing' };
    const { seen } = signedIn(character({ items: [coat, flower] }), {
      'POST /api/v1/asset/images': () => json(201, { id: sprite, format: 'png', byte_size: 3, width: 1, height: 1, url: '', created_at: '' }),
      [`GET /api/v1/asset/images/${sprite}`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/chat/studio/characters/${ID}?tab=sprites`);

    const form = await screen.findByRole('form', { name: '캐릭터 그림' });
    await userEvent.click(within(form).getByRole('button', { name: '캐릭터 그림 더하기' }));
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.upload(within(form).getByLabelText('캐릭터 그림 1'), new File(['png'], 'stand.png', { type: 'image/png' }));
    expect(await within(form).findByRole('img', { name: '캐릭터 그림 1' })).toHaveClass('image-picker__preview--checkered');
    await userEvent.type(within(form).getByLabelText('캐릭터 그림 1의 표정(선택)'), '웃음');
    // 차림은 옷만 고른다(꽃은 물건이라 나오지 않는다)
    expect(within(form).queryByRole('option', { name: '꽃' })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText('캐릭터 그림 1의 차림'), '외투');
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      sprites: [{ id: expect.stringMatching(/^sprite-[0-9a-f]{8}$/), image_id: sprite, expression: '웃음', outfit: 'coat' }],
    });
  });

  it('이벤트 씬의 조건을 호감도 단계로 바꾸면 대상을 비우고 단계에서 고른다', async () => {
    const image = '00000000-0000-4000-8000-00000000b002';
    const scene = { id: 'scene-1', title: '고백', image_id: image, description: '', collectible: true, when: { kind: 'reach_place', target: 'p1' } };
    const affection = { display: 'number', start: 0, model_step: 3, stages: [{ name: '처음', at: 0 }, { name: '연인', at: 80 }], rules: [] };
    Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:scene'), revokeObjectURL: vi.fn() });
    const { seen } = signedIn(
      character({ event_scenes: [scene], affection, places: [{ id: 'p1', name: '바다', description: '', image_id: null, backgrounds: {} }] }),
      { [`GET /api/v1/asset/images/${image}`]: () => new Response('png', { status: 200 }) },
    );
    renderApp(`/chat/studio/characters/${ID}?tab=scenes`);

    const form = await screen.findByRole('form', { name: '이벤트 씬' });
    expect(within(form).getByLabelText('이벤트 씬 1의 대상')).toHaveValue('p1');
    await userEvent.selectOptions(within(form).getByLabelText('이벤트 씬 1의 조건'), 'affection_stage');
    expect(within(form).getByLabelText('이벤트 씬 1의 대상')).toHaveValue('');
    expect(within(form).getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.selectOptions(within(form).getByLabelText('이벤트 씬 1의 대상'), '연인');
    await userEvent.click(within(form).getByLabelText('해금 대상'));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({
      event_scenes: [{ ...scene, collectible: false, when: { kind: 'affection_stage', target: '연인' } }],
    });
  });

  it('로어북을 고르기 목록에서 붙이고 차례를 바꿔 저장한다. 게시하지 않은 것과 목록에 없는 것을 알린다', async () => {
    const lore = (id: string, name: string, latest: number | null) => ({ id, name, entry_count: 2, latest_version: latest, updated_at: '2026-10-24T00:00:00Z' });
    const sea = lore('00000000-0000-4000-8000-00000000f001', '바다', 1);
    const city = lore('00000000-0000-4000-8000-00000000f002', '도시', null);
    const gone = '00000000-0000-4000-8000-00000000f009';
    const { seen } = signedIn(character({ lorebooks: [city.id, gone] }), {
      [`GET ${CHARACTERS}/${ID}/publish-check`]: () =>
        json(200, { ready: false, problems: ['start_missing', 'lorebook_unpublished', 'lorebook_missing'], removed: [] }),
      'GET /api/v1/asset/lorebooks': () => json(200, { items: [sea, city], total: 2 }),
    });
    renderApp(`/chat/studio/characters/${ID}`);

    const problems = await screen.findByRole('list', { name: '고칠 것' });
    await userEvent.click(within(problems).getAllByRole('button', { name: '로어북 탭으로' })[0] as HTMLElement);
    const form = screen.getByRole('form', { name: '로어북' });
    expect(form).toBeVisible();
    const attached = within(form).getByRole('list', { name: '붙인 로어북' });
    expect(await within(attached).findByText(/아직 게시하지 않았습니다/)).toBeInTheDocument();
    expect(within(attached).getByText(/목록에 없습니다/)).toBeInTheDocument();
    expect(within(attached).getByRole('link', { name: '도시' })).toHaveAttribute('href', `/chat/studio/lorebooks/${city.id}`);
    // 이미 붙인 것은 고르는 목록에 나오지 않는다
    expect(within(form).queryByRole('option', { name: '도시' })).not.toBeInTheDocument();

    await userEvent.click(within(form).getByRole('button', { name: '로어북 2 떼기' }));
    await userEvent.selectOptions(within(form).getByLabelText('붙일 로어북'), '바다');
    await userEvent.click(within(form).getByRole('button', { name: '붙이기' }));
    await userEvent.click(within(form).getByRole('button', { name: '바다을(를) 앞으로' }));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText('저장했습니다.')).toBeInTheDocument();
    expect(calls(seen, 'PATCH', `${CHARACTERS}/${ID}`)[0]?.body).toEqual({ lorebooks: [sea.id, city.id] });
    expect(calls(seen, 'GET', '/api/v1/asset/lorebooks')[0]?.url).toContain('limit=100');
  });

  it('남의 로어북이나 지워진 로어북을 붙이면(422) 알린다', async () => {
    const sea = { id: '00000000-0000-4000-8000-00000000f001', name: '바다', entry_count: 0, latest_version: 1, updated_at: '2026-10-24T00:00:00Z' };
    signedIn(character(), {
      'GET /api/v1/asset/lorebooks': () => json(200, { items: [sea], total: 1 }),
      [`PATCH ${CHARACTERS}/${ID}`]: () => json(422, { detail: '자기 로어북만 가리킬 수 있습니다.', code: 'lorebook_not_owned' }),
    });
    renderApp(`/chat/studio/characters/${ID}?tab=lorebooks`);

    const form = await screen.findByRole('form', { name: '로어북' });
    await userEvent.selectOptions(await within(form).findByLabelText('붙일 로어북'), '바다');
    await userEvent.click(within(form).getByRole('button', { name: '붙이기' }));
    await userEvent.click(within(form).getByRole('button', { name: '저장' }));

    expect(await within(form).findByText(/붙일 수 없는 로어북이 있습니다/)).toBeInTheDocument();
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
