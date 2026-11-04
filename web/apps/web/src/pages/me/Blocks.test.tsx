// web/apps/web/src/pages/me/Blocks.test.tsx
// 차단(#988). 막은 제작자와 태그를 공개 목록의 주소에 싣기(제작자는 쉼표로, 태그는 되풀이), 제작자 페이지의 "차단하기",
// 마이페이지의 "차단"에서 풀고 태그를 더하기, 상한의 알림. 바꾸면 내 정보의 blocks 가 바뀌어 목록을 다시 읽는다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { preferencesFor, setListingPreferences } from '../../api/listingPreferences';
import { REFRESH_PATH } from '../../api/refresh';
import type { Me } from '../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const CREATOR = '00000000-0000-4000-8000-0000000000c1';
const OTHER = '00000000-0000-4000-8000-0000000000c2';
const BLOCKS = '/api/v1/auth/me/blocks';
type Blocks = { creators: string[]; tags: string[] };

function me(blocks: Blocks) {
  return {
    nickname: '모험가',
    public_id: '00000000-0000-4000-8000-0000000000aa',
    username: 'p',
    email: 'e@x',
    identity: { verified: false, legal_adult: false, adult_content: false },
    guardian_consent: 'none',
    consents_pending: [],
    withdrawal_scheduled_at: null,
    content_settings: { show_adult_content: true, orientation: 'all' },
    bio: '',
    blocks,
  };
}

function signedIn(initial: Blocks, routes: Record<string, (request: SeenRequest) => Response> = {}) {
  let blocks = initial;
  const change = (next: Blocks) => {
    blocks = next;
    return json(200, blocks);
  };
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, me(blocks)),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 0, limit: 5 }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { count: 0 }),
    'GET /api/v1/auth/public-names': () => json(200, { names: [{ public_id: CREATOR, nickname: '이야기꾼' }] }),
    'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
    [`GET /api/v1/auth/creators/${CREATOR}`]: () => json(200, { public_id: CREATOR, nickname: '이야기꾼', bio: '' }),
    'GET /api/v1/asset/listings/characters': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/asset/listings/worlds': () => json(200, { items: [], total: 0 }),
    [`GET /api/v1/notification/me/follows/${CREATOR}`]: () => json(200, { following: false, follower_count: 0 }),
    [`PUT ${BLOCKS}/creators/${CREATOR}`]: () => change({ ...blocks, creators: [CREATOR, ...blocks.creators] }),
    [`DELETE ${BLOCKS}/creators/${CREATOR}`]: () => change({ ...blocks, creators: blocks.creators.filter((id) => id !== CREATOR) }),
    [`PUT ${BLOCKS}/tags/${encodeURIComponent('가,나')}`]: () => change({ ...blocks, tags: ['가,나', ...blocks.tags] }),
    [`DELETE ${BLOCKS}/tags/${encodeURIComponent('공포')}`]: () => change({ ...blocks, tags: blocks.tags.filter((tag) => tag !== '공포') }),
    ...routes,
  });
}

function lastListing(seen: SeenRequest[], path: string): URLSearchParams | undefined {
  const found = seen.filter((request) => request.method === 'GET' && request.url.startsWith(`${path}?`));
  const last = found.at(-1);
  return last ? new URL(last.url, 'http://x').searchParams : undefined;
}

afterEach(() => {
  setListingPreferences({});
  vi.restoreAllMocks();
});

describe('차단', () => {
  it('막은 제작자와 태그를 공개 목록의 주소에 싣는다', async () => {
    const { seen } = signedIn({ creators: [CREATOR, OTHER], tags: ['공포', '가,나'] });
    renderApp('/trpg');

    await vi.waitFor(() => {
      const query = lastListing(seen, '/api/v1/game/listings');
      expect(query?.get('exclude_creators')).toBe(`${CREATOR},${OTHER}`);
      expect(query?.getAll('exclude_tag')).toEqual(['공포', '가,나']);
    });
  });

  it('제작자 페이지에서 막고 풀면 목록을 다시 읽는다', async () => {
    const { seen } = signedIn({ creators: [], tags: [] });
    renderApp(`/creators/${CREATOR}`);

    await userEvent.click(await screen.findByRole('button', { name: '차단하기' }));

    expect(await screen.findByRole('button', { name: '차단 풀기' })).toHaveAttribute('aria-pressed', 'true');
    await vi.waitFor(() => expect(lastListing(seen, '/api/v1/game/listings')?.get('exclude_creators')).toBe(CREATOR));
    await userEvent.click(screen.getByRole('button', { name: '차단 풀기' }));
    await vi.waitFor(() => expect(lastListing(seen, '/api/v1/game/listings')?.has('exclude_creators')).toBe(false));
  });

  it('마이페이지에서 풀고 태그를 더한다', async () => {
    const { seen } = signedIn({ creators: [CREATOR], tags: ['공포'] });
    renderApp('/me');

    const section = (await screen.findByRole('heading', { name: '차단' })).closest('section') as HTMLElement;
    expect(await within(section).findByRole('link', { name: '이야기꾼' })).toHaveAttribute('href', `/creators/${CREATOR}`);
    expect(within(section).getByRole('heading', { name: '막은 태그 1/30' })).toBeInTheDocument();

    await userEvent.click(within(section).getAllByRole('button', { name: '풀기' })[1] as HTMLElement);
    await vi.waitFor(() => expect(within(section).getByRole('heading', { name: '막은 태그 0/30' })).toBeInTheDocument());
    await userEvent.type(within(section).getByRole('textbox', { name: '막을 태그' }), ' 가,나 ');
    await userEvent.click(within(section).getByRole('button', { name: '태그 막기' }));

    expect(await within(section).findByText('#가,나')).toBeInTheDocument();
    expect(seen.filter((request) => request.url.startsWith(BLOCKS)).map((request) => request.method)).toEqual(['DELETE', 'PUT']);
  });

  it('상한을 넘으면 그 까닭을 알린다', async () => {
    signedIn(
      { creators: [], tags: [] },
      { [`PUT ${BLOCKS}/creators/${CREATOR}`]: () => json(409, { detail: 'x', code: 'block_limit' }) },
    );
    renderApp(`/creators/${CREATOR}`);

    await userEvent.click(await screen.findByRole('button', { name: '차단하기' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('100명');
    expect(screen.getByRole('button', { name: '차단하기' })).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('막은 것을 실을 값', () => {
  it('비어 있으면 싣지 않고, 인증 서버가 아직 주지 않아도 깨지지 않는다', () => {
    expect(preferencesFor(me({ creators: [], tags: [] }) as unknown as Me)).toEqual({});
    const { blocks: _, ...older } = me({ creators: [], tags: [] });
    expect(preferencesFor(older as unknown as Me)).toEqual({});
    expect(preferencesFor(me({ creators: [CREATOR], tags: ['공포'] }) as unknown as Me)).toEqual({ exclude_creators: CREATOR, exclude_tag: ['공포'] });
  });
});
