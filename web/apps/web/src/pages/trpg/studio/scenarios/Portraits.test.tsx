// web/apps/web/src/pages/trpg/studio/scenarios/Portraits.test.tsx
// 프리젠의 캐릭터 그림(#983). 프리젠 창에서 그림을 올려 고르고 저장하면 image_id 를 보낸다. 내가 올린 그림을 고르고,
// 쓰이는 그림을 지우려 하면 쓰는 시나리오를 알린다. 목록의 줄 앞에 그림이 보인다. 실패의 글(순수한 함수).

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../../api/errors';
import { REFRESH_PATH } from '../../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../../test/fakeFetch';
import { renderApp } from '../../../../test/renderApp';
import { scenarioDetail } from '../../../../test/scenarioFixtures';
import { ME, RULES } from '../../../../test/tableFixtures';
import { describePortraitDeleteProblem, describePortraitUploadProblem, portraitUsers } from '../../portraits/portraitProblem';
import { describeScenarioSaveProblem } from './scenarioProblem';

const GAME = '/api/v1/game';
const ID = '00000000-0000-4000-8000-0000000000d1';
const RULEBOOK = '00000000-0000-4000-8000-0000000000d2';
const OLD = '00000000-0000-4000-8000-0000000000e1';
const NEW = '00000000-0000-4000-8000-0000000000e2';
const SCENARIO = `${GAME}/scenarios/${ID}`;

const KNIGHT = { name: '기사', description: '', sheet: null, items: [], money: 0, image_id: OLD };

function portrait(id: string) {
  return { id, created_at: '2026-11-05T00:00:00Z' };
}

function signedIn(deleting: () => Response = () => new Response(null, { status: 204 })) {
  let current = scenarioDetail({ rulebook_id: RULEBOOK, openings: ['종이 울린다.'], pregens: [KNIGHT] });
  let shelf = [portrait(OLD)];
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${GAME}/rulebooks/${RULEBOOK}`]: () =>
      json(200, { id: RULEBOOK, title: '규칙', description: '', gm_guide: '', visibility: 'private', created_at: '', updated_at: '', rules: RULES }),
    [`GET ${SCENARIO}`]: () => json(200, current),
    [`GET ${SCENARIO}/publish-check`]: () => json(200, { ready: true, problems: [] }),
    [`PATCH ${SCENARIO}`]: (request) => {
      current = { ...current, ...(request.body as Record<string, unknown>) };
      return json(200, current);
    },
    [`GET ${GAME}/portraits`]: () => json(200, { items: shelf, total: shelf.length }),
    [`POST ${GAME}/portraits`]: () => {
      shelf = [portrait(NEW), ...shelf];
      return json(201, portrait(NEW));
    },
    [`GET ${GAME}/portraits/${OLD}/image`]: () => new Response('png', { status: 200 }),
    [`GET ${GAME}/portraits/${NEW}/image`]: () => new Response('png', { status: 200 }),
    [`DELETE ${GAME}/portraits/${OLD}`]: deleting,
  });
}

function patches(seen: SeenRequest[]): { pregens: { image_id?: string | null }[] }[] {
  return seen.filter((request) => request.method === 'PATCH' && request.url === SCENARIO).map((request) => request.body as never);
}

async function openKnight() {
  const panel = within(await screen.findByRole('tabpanel', { name: '캐릭터' }));
  const list = within(await panel.findByRole('list', { name: '프리젠' }));
  await userEvent.click(list.getByRole('button', { name: '기사 고치기' }));
  return { list, dialog: within(await screen.findByRole('dialog')) };
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:portrait'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('프리젠의 캐릭터 그림', () => {
  it('목록의 줄 앞에 그림이 보이고, 새 그림을 올리면 고른 것이 되어 저장할 때 image_id 로 간다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const { list, dialog } = await openKnight();
    await vi.waitFor(() => expect(list.getByRole('img', { name: '기사의 그림' })).toHaveAttribute('src', 'blob:portrait'));
    expect(await dialog.findByRole('img', { name: '붙인 캐릭터 그림' })).toBeInTheDocument();

    await userEvent.click(dialog.getByRole('button', { name: '바꾸기' }));
    const shelf = within(dialog.getByRole('region', { name: '캐릭터 그림 고르기' }));
    expect(await shelf.findByRole('button', { name: '그림 1 고르기' })).toHaveAttribute('aria-pressed', 'true');
    await userEvent.upload(shelf.getByLabelText('새 그림 올리기'), new File(['png'], 'face.png', { type: 'image/png' }));
    await vi.waitFor(() => expect(dialog.queryByRole('region', { name: '캐릭터 그림 고르기' })).toBeNull());
    const upload = seen.find((request) => request.method === 'POST' && request.url.endsWith('/portraits'));
    expect(upload?.headers.get('Content-Type')).toBe('image/png');

    await userEvent.click(dialog.getByRole('button', { name: '저장' }));
    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pregens[0]?.image_id).toBe(NEW);
  });

  it('떼면 null 을 보낸다', async () => {
    const { seen } = signedIn();
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const { dialog } = await openKnight();
    await userEvent.click(dialog.getByRole('button', { name: '떼기' }));
    expect(dialog.getByText('붙인 그림이 없습니다.')).toBeInTheDocument();
    await userEvent.click(dialog.getByRole('button', { name: '저장' }));

    await vi.waitFor(() => expect(patches(seen)).toHaveLength(1));
    expect(patches(seen)[0]?.pregens[0]?.image_id).toBeNull();
  });

  it('쓰이는 그림을 지우려 하면 까닭과 쓰는 시나리오로 가는 길을 보인다', async () => {
    signedIn(() => json(409, { detail: '못 지운다', code: 'portrait_in_use', scenarios: [{ id: ID, title: '수도원의 밤' }] }));
    renderApp(`/trpg/studio/scenarios/${ID}?tab=characters`);

    const { dialog } = await openKnight();
    await userEvent.click(dialog.getByRole('button', { name: '바꾸기' }));
    const shelf = within(dialog.getByRole('region', { name: '캐릭터 그림 고르기' }));
    await userEvent.click(await shelf.findByRole('button', { name: '그림 1 지우기' }));
    await userEvent.click(shelf.getByRole('button', { name: '그림 1 지우기 확인' }));

    expect(await shelf.findByText(/이 그림을 쓰는 시나리오가 있습니다/)).toBeInTheDocument();
    expect(shelf.getByRole('link', { name: '수도원의 밤' })).toHaveAttribute('href', `/trpg/studio/scenarios/${ID}?tab=characters`);
  });
});

describe('캐릭터 그림의 실패', () => {
  it('올리기: 100장이 차면, asset 이 안 되면, 형식이 틀리면', () => {
    const limit = new ApiError({ status: 409, detail: '', code: 'portrait_limit' });
    expect(describePortraitUploadProblem(limit).message).toContain('100장까지');
    expect(describePortraitUploadProblem(new ApiError({ status: 503, detail: '', code: 'asset_unavailable' })).message).toContain('지금은 그림을 올릴 수 없습니다');
    expect(describePortraitUploadProblem(new ApiError({ status: 415, detail: '', code: 'image_format' })).message).toBe('PNG, JPEG, WebP 그림만 올릴 수 있습니다.');
  });

  it('지우기: 쓰는 시나리오들과 없는 그림', () => {
    const inUse = new ApiError({ status: 409, detail: '', code: 'portrait_in_use', body: { scenarios: [{ id: 's1', title: '밤' }] } });
    expect(portraitUsers(inUse)).toEqual([{ id: 's1', title: '밤' }]);
    expect(portraitUsers(new ApiError({ status: 404, detail: '' }))).toEqual([]);
    expect(describePortraitDeleteProblem(new ApiError({ status: 404, detail: '', code: 'portrait_not_found' })).message).toBe('이미 지웠거나 찾을 수 없는 그림입니다.');
  });

  it('저장: 프리젠의 그림이 내 그림이 아니면 다시 고르게 한다', () => {
    const error = new ApiError({ status: 422, detail: 'pregens.image_id 가 가리키는 자산을 찾을 수 없습니다.' });
    expect(describeScenarioSaveProblem(error).message).toContain('그림을 다시 골라 주세요');
  });
});
