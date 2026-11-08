// web/apps/web/src/pages/trpg/studio/scenarios/Pictures.test.tsx
// 시나리오의 그림 탭(#1163). 붙인 로어북의 장소, 인물, 사건 항목마다 그림 칸이 있고, 붙이고 떼어 저장하면 pictures 를 통째로 보낸다.
// 장소에는 때마다의 배경을 붙인다. 붙일 수 없는 항목의 그림은 따로 모아 뗀다. 저장과 게시 점검의 실패 글, 입력의 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME } from '../../../../test/tableFixtures';
import { MAX_PICTURES, strayPictures, toPicturesBody, withoutTimes, withPicture, withTimePicture } from './picturesForm';
import { problemLine } from './publishProblems';
import { describeScenarioSaveProblem } from './scenarioProblem';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const LOREBOOK = '00000000-0000-4000-8000-0000000000d3';
const HALL = '00000000-0000-4000-8000-0000000000f1';
const GUARD = '00000000-0000-4000-8000-0000000000f2';
const FIRE = '00000000-0000-4000-8000-0000000000f3';
const SWORD = '00000000-0000-4000-8000-0000000000f4';
const GONE = '00000000-0000-4000-8000-0000000000f5';
const OLD = '00000000-0000-4000-8000-0000000000e1';
const NEW = '00000000-0000-4000-8000-0000000000e2';
const SCENARIO = `${GAME}/scenarios/${ID}`;

function entry(id: string, name: string, kind: string) {
  return { id, lorebook_id: LOREBOOK, kind, name, aliases: [], content: '', created_at: '', updated_at: '' };
}

type Picture = { entry_id: string; image_id: string; by_time?: Record<string, string> };

function signedIn(pictures: Picture[]) {
  let current = scenarioDetail({ lorebook_ids: [LOREBOOK], pictures });
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/lorebooks/${LOREBOOK}/entries`]: () =>
      json(200, [entry(HALL, '대회당', 'place'), entry(GUARD, '늙은 문지기', 'person'), entry(FIRE, '종탑의 불', 'event'), entry(SWORD, '녹슨 검', 'item')]),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${GAME}/portraits`]: () => json(200, { items: [{ id: OLD, created_at: '' }, { id: NEW, created_at: '' }], total: 2 }),
    [`GET ${GAME}/portraits/${OLD}/image`]: () => new Response('png', { status: 200 }),
    [`GET ${GAME}/portraits/${NEW}/image`]: () => new Response('png', { status: 200 }),
  });
}

function patches(seen: SeenRequest[]): { pictures: Picture[] }[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as never);
}

async function openForm() {
  renderApp(`/trpg/studio/scenarios/${ID}?tab=pictures`);
  const panel = within(await screen.findByRole('tabpanel', { name: '그림' }));
  return within(await panel.findByRole('form', { name: '그림' }));
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('시나리오의 그림 탭', () => {
  it('장소, 인물, 사건마다 그림 칸이 있고 물건에는 없다. 사건에 그림을 붙여 저장하면 목록을 통째로 보낸다', async () => {
    const { seen } = signedIn([{ entry_id: HALL, image_id: OLD }]);
    const form = await openForm();

    expect(await form.findByRole('group', { name: '대회당의 그림' })).toBeInTheDocument();
    expect(form.getByRole('group', { name: '늙은 문지기의 그림' })).toBeInTheDocument();
    expect(form.queryByRole('group', { name: '녹슨 검의 그림' })).toBeNull();
    expect(within(form.getByRole('group', { name: '대회당의 그림' })).getByRole('img', { name: '붙인 대회당의 그림' })).toBeInTheDocument();

    const fire = within(form.getByRole('group', { name: '종탑의 불의 그림' }));
    await userEvent.click(fire.getByRole('button', { name: '그림 붙이기' }));
    await userEvent.click(await fire.findByRole('button', { name: '그림 2 고르기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pictures).toEqual([
      { entry_id: HALL, image_id: OLD, by_time: {} },
      { entry_id: FIRE, image_id: NEW, by_time: {} },
    ]);
  });

  it('붙일 수 없는 항목(로어북에 없는 항목, 물건)의 그림은 따로 모이고, 떼고 저장하면 빠진다', async () => {
    const { seen } = signedIn([
      { entry_id: GONE, image_id: OLD },
      { entry_id: SWORD, image_id: NEW },
      { entry_id: GUARD, image_id: OLD },
    ]);
    const form = await openForm();

    const stray = within(await form.findByRole('list', { name: '붙일 수 없는 항목의 그림' }));
    expect(stray.getAllByRole('listitem')).toHaveLength(2);
    await userEvent.click(stray.getByRole('button', { name: '붙일 수 없는 그림 1 떼기' }));
    await userEvent.click(within(form.getByRole('group', { name: '늙은 문지기의 그림' })).getByRole('button', { name: '떼기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pictures).toEqual([{ entry_id: SWORD, image_id: NEW, by_time: {} }]);
  });

  it('장소에 기본 그림이 있으면 때마다의 배경을 펼쳐 붙이고, 저장하면 by_time 으로 간다. 기본 그림이 없으면 칸이 없다', async () => {
    const { seen } = signedIn([{ entry_id: HALL, image_id: OLD, by_time: { night: OLD } }]);
    const form = await openForm();

    const times = within((await form.findByText(/대회당의 때마다의 배경/)).closest('details') as HTMLElement);
    expect(times.getByText('대회당의 때마다의 배경 (1 / 5)')).toBeInTheDocument();
    const dawn = within(times.getByRole('group', { name: '대회당의 새벽 배경' }));
    await userEvent.click(dawn.getByRole('button', { name: '그림 붙이기' }));
    await userEvent.click(await dawn.findByRole('button', { name: '그림 2 고르기' }));
    // 인물과 사건에는 때마다의 칸이 없다
    expect(form.queryByText(/늙은 문지기의 때마다의 배경/)).toBeNull();
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pictures).toEqual([{ entry_id: HALL, image_id: OLD, by_time: { dawn: NEW, night: OLD } }]);
  });

  it('장소가 아닌 항목의 때마다의 그림은 떼게 한다', async () => {
    const { seen } = signedIn([{ entry_id: GUARD, image_id: OLD, by_time: { day: NEW } }]);
    const form = await openForm();

    await userEvent.click(await form.findByRole('button', { name: '늙은 문지기의 때마다의 그림 떼기' }));
    await userEvent.click(form.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pictures).toEqual([{ entry_id: GUARD, image_id: OLD, by_time: {} }]);
  });
});

describe('그림 탭의 입력과 실패', () => {
  it('바꾸면 자리와 때마다의 그림을 지키고, 새 항목은 끝에, 가득 차면 붙이지 않는다', () => {
    const rows = [
      { entryId: 'a', imageId: '1', byTime: { night: '5' } },
      { entryId: 'b', imageId: '2', byTime: {} },
    ];
    expect(withPicture(rows, 'a', '9')).toEqual([
      { entryId: 'a', imageId: '9', byTime: { night: '5' } },
      { entryId: 'b', imageId: '2', byTime: {} },
    ]);
    expect(withPicture(rows, 'c', '3').at(-1)).toEqual({ entryId: 'c', imageId: '3', byTime: {} });
    expect(withPicture(rows, 'a', null)).toEqual([{ entryId: 'b', imageId: '2', byTime: {} }]);
    const full = Array.from({ length: MAX_PICTURES }, (_, index) => ({ entryId: `e${index}`, imageId: 'x', byTime: {} }));
    expect(withPicture(full, 'new', 'x')).toHaveLength(MAX_PICTURES);
    expect(strayPictures(rows, ['a'])).toEqual([{ entryId: 'b', imageId: '2', byTime: {} }]);
  });

  it('때마다의 그림: 붙이고 떼고, 줄이 없으면 그대로, 보낼 때는 하루의 차례', () => {
    const rows = [{ entryId: 'a', imageId: '1', byTime: {} }];
    const timed = withTimePicture(withTimePicture(rows, 'a', 'night', '7'), 'a', 'dawn', '6');
    expect(toPicturesBody(timed).pictures?.[0]?.by_time).toEqual({ dawn: '6', night: '7' });
    expect(Object.keys(toPicturesBody(timed).pictures?.[0]?.by_time ?? {})).toEqual(['dawn', 'night']);
    expect(withTimePicture(timed, 'a', 'night', null)[0]?.byTime).toEqual({ dawn: '6' });
    expect(withTimePicture(rows, 'zz', 'day', '1')).toEqual(rows);
    expect(withoutTimes(timed, 'a')[0]?.byTime).toEqual({});
  });

  it('저장: 그림이 내 그림이 아니면 다시 고르게 하고, 게시 점검의 문제는 그림 탭을 가리킨다', () => {
    const error = new ApiError({ status: 422, detail: 'pictures.image_id 가 가리키는 자산을 찾을 수 없습니다.' });
    expect(describeScenarioSaveProblem(error).message).toContain('그림을 다시 골라 주세요');
    expect(problemLine('picture_entry_missing').section).toBe('pictures');
    expect(problemLine('picture_wrong_kind').section).toBe('pictures');
    expect(problemLine('picture_time_not_place').section).toBe('pictures');
  });
});
