// web/apps/web/src/pages/story/studio/StoryWorldStudio.test.tsx
// 세계관 만들기(D7)의 첫 조각. 마이페이지에서 가기, 빈 목록에서 만들기 → 고치기와 게시 점검(막는 것에서 탭으로, 알리는 것),
// 운영자만 만드는 때(403), 기본·진행·지도·물건의 저장 본문(저장하면 점검을 다시 읽는다), 게시와 알리는 것.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';

const WORLDS = '/api/v1/asset/worlds';
const ID = '00000000-0000-4000-8000-0000000000f7';
const AT = '2026-10-28T00:00:00Z';

function world(extra: Record<string, unknown> = {}) {
  return {
    id: ID,
    name: '여름 학교',
    intro_html: '',
    tags: [],
    image_id: null,
    rating: 'all',
    visibility: 'private',
    slots: [
      { id: 'morning', name: '아침', start_hour: 7 },
      { id: 'night', name: '밤', start_hour: 21 },
    ],
    start_slot: 'morning',
    deadline_days: null,
    after_ending: 'end',
    show: { reveal: 'shown', map: 'shown', panel: ['intro', 'age', 'gender', 'affection'] },
    places: [],
    paths: [],
    start_place: null,
    items: [],
    start_items: [],
    cast: [],
    events: [],
    endings: [],
    lorebooks: [],
    latest_version: null,
    published_at: null,
    created_at: AT,
    updated_at: AT,
    ...extra,
  };
}

type Routes = Record<string, (request: SeenRequest) => Response>;
type World = ReturnType<typeof world>;

/** 로그인한 운영자와, 받은 것을 기억하는 가짜 asset 서버 */
function signedIn(initial: World | null = world(), routes: Routes = {}) {
  let current = initial ?? world();
  const check = () => {
    const problems = current.start_place === null ? ['start_place_missing', 'cast_empty'] : ['cast_empty'];
    return { ready: false, problems, warnings: current.places.length > 1 ? ['place_unreachable'] : [], removed: [] };
  };
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '만드는 사람', identity: { adult_content: false } }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    [`GET ${WORLDS}`]: () => json(200, initial ? { items: [{ id: ID, name: current.name, rating: 'all', visibility: 'private', latest_version: null, updated_at: AT }], total: 1 } : { items: [], total: 0 }),
    [`POST ${WORLDS}`]: (request) => {
      current = world({ name: (request.body as { name: string }).name });
      return json(201, current);
    },
    [`GET ${WORLDS}/${ID}`]: () => json(200, current),
    [`PATCH ${WORLDS}/${ID}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) } as World;
      return json(200, current);
    },
    [`GET ${WORLDS}/${ID}/publish-check`]: () => json(200, check()),
    [`GET ${WORLDS}/${ID}/versions`]: () => json(200, []),
    'GET /api/v1/asset/lorebooks': () => json(200, { items: [], total: 0 }),
    ...routes,
  });
}

function patches(seen: SeenRequest[]): unknown[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === `${WORLDS}/${ID}`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('세계관 만들기', () => {
  it('마이페이지에서 가서 빈 목록에서 만들고, 고치기에서 게시 점검의 막는 것과 알리는 것을 보고 그 탭으로 간다', async () => {
    const { seen } = signedIn(null);
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: 'story 세계관 만들기' }));
    expect(await screen.findByText('아직 만든 세계관이 없습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '첫 세계관 만들기' }));
    await userEvent.type(await screen.findByLabelText('이름'), '여름 학교');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));

    expect(await screen.findByText('만들었습니다.')).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'POST' && request.url === WORLDS).map((request) => request.body)).toEqual([{ name: '여름 학교' }]);
    const problems = within(await screen.findByRole('list', { name: '고칠 것' }));
    expect(problems.getByText('인물이 하나도 없습니다.')).toBeInTheDocument();
    await userEvent.click(problems.getByRole('button', { name: '진행 탭으로' }));
    expect(screen.getByRole('tab', { name: '진행' })).toHaveAttribute('aria-selected', 'true');
  });

  it('운영자가 아니면 만들기에서 막힌 까닭을 알린다', async () => {
    signedIn(null, { [`POST ${WORLDS}`]: () => json(403, { detail: 'x', code: 'operator_only' }) });
    renderApp('/story/studio/worlds/new');

    await userEvent.type(await screen.findByLabelText('이름'), '여름 학교');
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));
    expect(await screen.findByText('지금은 운영자만 세계관을 만들고 공개로 둘 수 있습니다.')).toBeInTheDocument();
  });

  it('기본 탭은 이름, 태그, 등급, 공개 범위, 그림만 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/story/studio/worlds/${ID}`);

    const basics = await screen.findByRole('form', { name: '기본' });
    await userEvent.type(within(basics).getByLabelText('태그(쉼표로 나눈다)'), '학원, 청춘, 학원');
    await userEvent.click(within(basics).getByRole('button', { name: '저장' }));
    await waitFor(() => expect(patches(seen)).toEqual([{ name: '여름 학교', tags: ['학원', '청춘'], rating: 'all', visibility: 'private', image_id: null }]));
  });

  it('진행 탭은 시간대의 차례를 검사하고, 기한·엔딩 뒤·보이기·시작 장소와 소지품을 보낸다', async () => {
    const { seen } = signedIn(world({ places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: {} }], items: [{ id: 'flower', name: '꽃', description: '', consumable: false, image_id: null }] }));
    renderApp(`/story/studio/worlds/${ID}?tab=progress`);

    const progress = await screen.findByRole('form', { name: '진행' });
    const form = within(progress);
    await userEvent.click(form.getByRole('button', { name: '시간대 더하기' }));
    await userEvent.type(form.getByLabelText('시간대 3의 이름'), '새벽');
    await userEvent.type(form.getByLabelText('시간대 3의 시작 시각(시)'), '5');
    expect(form.getByText('시작 시각은 앞의 시간대보다 늦어야 합니다.')).toBeInTheDocument();
    expect(form.getByRole('button', { name: '저장' })).toBeDisabled();
    await userEvent.click(form.getByRole('button', { name: '시간대 3 지우기' }));

    await userEvent.type(form.getByLabelText('기한(날 수, 비우면 없음)'), '30');
    await userEvent.selectOptions(form.getByLabelText('엔딩 뒤'), 'epilogue');
    await userEvent.selectOptions(form.getByLabelText('인물의 공개'), 'silhouette');
    await userEvent.click(form.getByLabelText('나이'));
    await userEvent.selectOptions(form.getByLabelText('시작 장소'), 'park');
    await userEvent.click(form.getByRole('button', { name: '소지품 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('소지품 1의 물건'), 'flower');
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    await waitFor(() =>
      expect(patches(seen)).toEqual([
        {
          slots: [
            { id: 'morning', name: '아침', start_hour: 7 },
            { id: 'night', name: '밤', start_hour: 21 },
          ],
          start_slot: 'morning',
          deadline_days: 30,
          after_ending: 'epilogue',
          show: { reveal: 'silhouette', map: 'shown', panel: ['intro', 'gender', 'affection'] },
          start_place: 'park',
          start_items: [{ item: 'flower', count: 1 }],
        },
      ]),
    );
  });

  it('지도 탭은 장소와 길을 보내고, 시작 장소를 지우면 시작 장소를 비운다. 알리는 것이 점검에 보인다', async () => {
    const { seen } = signedIn(world({ places: [{ id: 'park', name: '공원', description: '', image_id: null, backgrounds: { morning: '00000000-0000-4000-8000-0000000000a1', gone: '00000000-0000-4000-8000-0000000000a2' } }], start_place: 'park' }));
    renderApp(`/story/studio/worlds/${ID}?tab=map`);

    const form = within(await screen.findByRole('form', { name: '지도' }));
    await userEvent.click(form.getByRole('button', { name: '장소 더하기' }));
    await userEvent.type(form.getByLabelText('장소 2의 이름'), '학교');
    await userEvent.click(form.getByRole('button', { name: '길 더하기' }));
    await userEvent.selectOptions(form.getByLabelText('길 1의 한쪽'), 'park');
    const school = within(form.getByLabelText('길 1의 다른 쪽')).getByRole('option', { name: '학교' }) as HTMLOptionElement;
    await userEvent.selectOptions(form.getByLabelText('길 1의 다른 쪽'), school.value);
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    const first = patches(seen)[0] as { places: { id: string; name: string; backgrounds: Record<string, string> }[]; paths: unknown[]; start_place?: unknown };
    expect(first.places.map((place) => place.name)).toEqual(['공원', '학교']);
    expect(first.places[0]?.backgrounds).toEqual({ morning: '00000000-0000-4000-8000-0000000000a1' });
    expect(first.paths).toEqual([{ a: 'park', b: school.value, minutes: 10 }]);
    expect(first).not.toHaveProperty('start_place');
    expect(await screen.findByText('시작 장소에서 길로 닿지 않는 장소가 있습니다.')).toBeInTheDocument();

    await userEvent.click(form.getByRole('button', { name: '장소 1 지우기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(patches(seen)).toHaveLength(2));
    expect(patches(seen)[1]).toMatchObject({ paths: [], start_place: null });
  });

  it('물건 탭은 물건을 보내고, 시작 소지품인 물건을 지우면 소지품도 함께 보낸다', async () => {
    const { seen } = signedIn(world({ items: [{ id: 'flower', name: '꽃', description: '', consumable: false, image_id: null }], start_items: [{ item: 'flower', count: 2 }] }));
    renderApp(`/story/studio/worlds/${ID}?tab=items`);

    const form = within(await screen.findByRole('form', { name: '물건' }));
    expect(form.getByText('시작 소지품에서도 빠집니다.')).toBeInTheDocument();
    await userEvent.click(form.getByRole('button', { name: '물건 1 지우기' }));
    await userEvent.click(form.getByRole('button', { name: '물건 더하기' }));
    await userEvent.type(form.getByLabelText('물건 1의 이름'), '편지');
    await userEvent.click(form.getByLabelText('쓰면 하나 없어진다'));
    await userEvent.click(form.getByRole('button', { name: '저장' }));
    await waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]).toMatchObject({ items: [{ name: '편지', description: '', consumable: true, image_id: null }], start_items: [] });
  });

  it('게시하면 판의 번호와 알리는 것을 보인다', async () => {
    const { seen } = signedIn(world({ start_place: 'park' }), {
      [`GET ${WORLDS}/${ID}/publish-check`]: () => json(200, { ready: true, problems: [], warnings: [], removed: [] }),
      [`POST ${WORLDS}/${ID}/versions`]: () => json(201, { id: 'v1', number: 1, note: '첫 판', created_at: AT, document: {}, removed: [], warnings: ['cast_never_present'] }),
    });
    renderApp(`/story/studio/worlds/${ID}?tab=publish`);

    const form = within(await screen.findByRole('form', { name: '게시' }));
    await userEvent.type(form.getByLabelText('바뀐 것(선택)'), '첫 판');
    await waitFor(() => expect(form.getByRole('button', { name: '게시' })).toBeEnabled());
    await userEvent.click(form.getByRole('button', { name: '게시' }));
    expect(await form.findByText(/1판을 게시했습니다/)).toBeInTheDocument();
    expect(form.getByText('어디에도 나오지 않는 인물이 있습니다.')).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'POST' && request.url === `${WORLDS}/${ID}/versions`).map((request) => request.body)).toEqual([{ note: '첫 판' }]);
  });
});
