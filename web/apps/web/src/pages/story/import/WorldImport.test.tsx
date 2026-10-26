// web/apps/web/src/pages/story/import/WorldImport.test.tsx
// JSON 으로 세계관 넣기. 운영자가 아니면 없는 화면이고 길도 없다. 운영자는 시험용 세계관을 받아 인물마다 내 캐릭터를 고르고(고르기 전에는 못 만듦)
// 만들고 게시한다(알리는 것). 게시를 막는 것(409 problems)과 만들기의 칸 오류를 줄마다 보인다. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../../api/errors';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { SAMPLE_WORLD } from './sampleWorld';
import { allChosen, castSlots, describeImportProblem, parseWorld, warningText, withCharacters } from './worldImport';

const WORLD = '00000000-0000-4000-8000-00000000b701';
const CHARACTER = '00000000-0000-4000-8000-00000000c701';
const AT = '2026-10-26T03:00:00Z';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

function signedInAs(roles: string[], routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
    'GET /api/v1/story/conversations': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/worlds': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/characters': () =>
      json(200, {
        items: [
          { id: CHARACTER, name: '하나', latest_version: 2, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
          { id: '00000000-0000-4000-8000-00000000c702', name: '초안만', latest_version: null, rating: 'all', visibility: 'private', hidden_at: null, updated_at: AT },
        ],
        total: 2,
      }),
    ...routes,
  });
}

function posts(seen: SeenRequest[], url: string): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === url).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('JSON 으로 세계관 넣기', () => {
  it('운영자가 아니면 없는 화면이고, 내 이야기에 길도 없다', async () => {
    signedInAs([]);
    renderApp('/story');
    expect(await screen.findByText('게시한 세계관이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'JSON 으로 세계관 넣기' })).toBeNull();
  });

  it('운영자는 시험용 세계관에 내 캐릭터를 끼워 만들고 게시한다', async () => {
    const { seen } = signedInAs(['operator'], {
      'POST /api/v1/asset/worlds': () => json(201, { id: WORLD, name: '시험 마을' }),
      [`POST /api/v1/asset/worlds/${WORLD}/versions`]: () => json(201, { id: 'v1', number: 1, note: '', created_at: AT, document: {}, removed: [], warnings: ['place_unreachable'] }),
    });
    renderApp('/story');

    await userEvent.click(await screen.findByRole('link', { name: 'JSON 으로 세계관 넣기' }));
    expect(await screen.findByRole('heading', { name: 'JSON 으로 세계관 넣기' })).toBeInTheDocument();
    expect((screen.getByLabelText('세계관 JSON') as HTMLTextAreaElement).value).toContain('시험 마을');
    const create = screen.getByRole('button', { name: '만들기' });
    expect(create).toBeDisabled();

    const pick = await screen.findByLabelText('인물 hana');
    await within(pick).findByRole('option', { name: '하나 (2판)' });
    expect(within(pick).queryByText(/초안만/)).toBeNull();
    await userEvent.selectOptions(pick, CHARACTER);
    await userEvent.click(create);
    expect(await screen.findByText(/"시험 마을"을 만들었습니다/)).toBeInTheDocument();
    const body = posts(seen, '/api/v1/asset/worlds')[0] as { cast: { id: string; character_id: string }[]; name: string };
    expect(body.name).toBe('시험 마을');
    expect(body.cast[0]?.character_id).toBe(CHARACTER);

    await userEvent.type(screen.getByLabelText('이번 판의 메모(비워도 됩니다)'), '첫 판');
    await userEvent.click(screen.getByRole('button', { name: '게시' }));
    expect(await screen.findByText(/1판을 게시했습니다/)).toBeInTheDocument();
    expect(screen.getByText('시작 장소에서 길로 닿지 않는 장소가 있습니다.')).toBeInTheDocument();
    expect(posts(seen, `/api/v1/asset/worlds/${WORLD}/versions`)).toEqual([{ note: '첫 판' }]);
  });

  it('게시를 막는 것과 JSON 이 아닌 글을 알린다', async () => {
    signedInAs(['operator'], {
      'POST /api/v1/asset/worlds': () => json(201, { id: WORLD, name: '시험 마을' }),
      [`POST /api/v1/asset/worlds/${WORLD}/versions`]: () => json(409, { detail: '게시할 조건을 갖추지 못했습니다.', problems: ['character_unpublished', 'ending_missing'] }),
    });
    renderApp('/story/worlds/import');

    await screen.findByRole('option', { name: '하나 (2판)' });
    await userEvent.selectOptions(screen.getByLabelText('인물 hana'), CHARACTER);
    await userEvent.click(screen.getByRole('button', { name: '만들기' }));
    await userEvent.click(await screen.findByRole('button', { name: '게시' }));
    const problems = within(await screen.findByRole('list', { name: '문제' }));
    expect(problems.getByText('인물이 가리킨 캐릭터를 게시한 적이 없습니다. 캐릭터를 먼저 게시해 주세요.')).toBeInTheDocument();
    expect(problems.getAllByRole('listitem')).toHaveLength(2);

    const area = screen.getByLabelText('세계관 JSON');
    await userEvent.clear(area);
    await userEvent.type(area, '[[');
    expect(screen.getByText(/JSON 으로 읽지 못했습니다|세계관 하나/)).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  it('읽기, 인물, 끼우기, 문장', () => {
    expect(parseWorld('[1]')).toEqual({ error: '세계관 하나(중괄호로 감싼 객체)를 넣어 주세요.' });
    expect('error' in parseWorld('{')).toBe(true);
    const parsed = parseWorld(JSON.stringify(SAMPLE_WORLD));
    if (!('world' in parsed)) throw new Error('시험용 세계관을 읽지 못했다');
    const slots = castSlots(parsed.world);
    expect(slots).toEqual([{ index: 0, id: 'hana' }]);
    expect(allChosen(slots, {})).toBe(false);
    expect(allChosen(slots, { 0: CHARACTER })).toBe(true);
    const filled = withCharacters(parsed.world, { 0: CHARACTER }) as { cast: { character_id: string }[] };
    expect(filled.cast[0]?.character_id).toBe(CHARACTER);
    expect((SAMPLE_WORLD.cast as { character_id: string }[])[0]?.character_id).not.toBe(CHARACTER);
    expect(castSlots({ cast: 'x' })).toEqual([]);

    expect(describeImportProblem(new ApiError({ status: 403, detail: 'x', code: 'operator_only' }))).toEqual(['세계관은 지금 운영자만 만듭니다.']);
    expect(describeImportProblem(new ApiError({ status: 422, detail: 'x', code: 'character_not_owned' }))[0]).toMatch(/내 캐릭터가 아닌/);
    expect(describeImportProblem(new ApiError({ status: 422, detail: 'x', fields: { 'cast.0.id': ['너무 깁니다'] }, body: { errors: {} } }))).toEqual(['cast.0.id: 너무 깁니다']);
    expect(describeImportProblem(new ApiError({ status: 409, detail: 'x', body: { problems: ['new_problem'] } }))).toEqual(['new_problem']);
    expect(warningText('ending_unreachable')).toBe('고를 일이 없는 엔딩이 있습니다.');
  });
});
