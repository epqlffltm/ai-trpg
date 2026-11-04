// web/apps/web/src/layout/ListingPreferences.test.tsx
// 목록 거르기(#986, #987). 내 정보의 설정을 공개 목록의 주소에 싣기, 설정 화면에서 바꾸면 저장하고 목록을 다시 읽기,
// 성인 확인 전에는 성인 작품 표시를 두지 않기, 머리의 "19" 스위치. 내 정보에서 실을 값을 고르는 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { preferencesFor, setListingPreferences } from '../api/listingPreferences';
import { REFRESH_PATH } from '../api/refresh';
import type { Me } from '../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { ME } from '../test/tableFixtures';
import { isPublicListing } from './ListingPreferencesSync';

const UNVERIFIED = { verified: false, legal_adult: false, adult_content: false };
const ADULT = { verified: true, legal_adult: true, adult_content: true };
const SETTINGS = '/api/v1/auth/me/content-settings';

type Settings = { show_adult_content: boolean; orientation: 'all' | 'male' | 'female' };

function me(identity: typeof ADULT, settings: Settings) {
  return {
    nickname: '모험가',
    public_id: ME,
    username: 'p',
    email: 'e@x',
    identity,
    guardian_consent: 'none',
    consents_pending: [],
    withdrawal_scheduled_at: null,
    content_settings: settings,
  };
}

/** 로그인한 사람. 설정을 바꾸면 그 값을 내 정보에도 둔다 */
function signedIn(identity: typeof ADULT, initial: Settings) {
  let settings = initial;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, me(identity, settings)),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notifications/unread-count': () => json(200, { count: 0 }),
    'GET /api/v1/game/listings': () => json(200, { items: [], total: 0 }),
    [`PATCH ${SETTINGS}`]: (request) => {
      settings = { ...settings, ...(request.body as Partial<Settings>) };
      return json(200, settings);
    },
  });
}

function listingQueries(seen: SeenRequest[]): URLSearchParams[] {
  return seen.filter((request) => request.method === 'GET' && request.url.startsWith('/api/v1/game/listings?')).map((request) => new URL(request.url, 'http://x').searchParams);
}

afterEach(() => {
  setListingPreferences({});
  vi.restoreAllMocks();
});

describe('목록 거르기', () => {
  it('내 정보의 설정을 공개 목록(시나리오 탐색)의 주소에 싣고, 바꾸면 다시 읽는다', async () => {
    const { seen } = signedIn(ADULT, { show_adult_content: false, orientation: 'female' });
    renderApp('/trpg');

    await vi.waitFor(() => {
      const last = listingQueries(seen).at(-1);
      expect(last?.get('hide_adult')).toBe('true');
      expect(last?.get('orientation')).toBe('female');
    });

    // 머리의 "19"로 다시 켜면 이미 읽은 목록을 설정 없이 다시 읽는다
    await userEvent.click(screen.getByRole('button', { name: '성인 작품 표시' }));
    await vi.waitFor(() => {
      const last = listingQueries(seen).at(-1);
      expect(last?.has('hide_adult')).toBe(false);
      expect(last?.get('orientation')).toBe('female');
    });
  });

  it('설정 화면에서 바꾸면 저장한다. 성인 확인 전에는 성인 작품 표시가 없다', async () => {
    const { seen } = signedIn(UNVERIFIED, { show_adult_content: true, orientation: 'all' });
    renderApp('/settings');

    const section = (await screen.findByRole('heading', { name: '목록 거르기' })).closest('section') as HTMLElement;
    expect(within(section).queryByRole('checkbox', { name: /성인 작품 표시/ })).not.toBeInTheDocument();
    expect(within(section).getByText(/성인 확인을 마치면/)).toBeInTheDocument();

    await userEvent.selectOptions(within(section).getByRole('combobox', { name: '성향' }), 'male');
    await vi.waitFor(() => expect(seen.find((request) => request.method === 'PATCH')?.body).toEqual({ orientation: 'male' }));
    await vi.waitFor(() => expect(within(section).getByRole('combobox', { name: '성향' })).toHaveValue('male'));
    expect(screen.queryByRole('button', { name: '성인 작품 표시' })).not.toBeInTheDocument();
  });

  it('성인 확인을 했으면 머리의 "19"로 성인 작품 표시를 바꾼다. 설정 화면의 값과 같다', async () => {
    const { seen } = signedIn(ADULT, { show_adult_content: true, orientation: 'all' });
    renderApp('/settings');

    const toggle = await screen.findByRole('button', { name: '성인 작품 표시' });
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('checkbox', { name: /성인 작품 표시/ })).toBeChecked();

    await userEvent.click(toggle);
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '성인 작품 표시' })).toHaveAttribute('aria-pressed', 'false'));
    expect(seen.find((request) => request.method === 'PATCH')?.body).toEqual({ show_adult_content: false });
    expect(screen.getByRole('checkbox', { name: /성인 작품 표시/ })).not.toBeChecked();
  });

  it('로그인하지 않았으면 설정 화면에 목록 거르기가 없다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp('/settings');

    await screen.findByRole('heading', { name: '설정' });
    expect(screen.queryByRole('heading', { name: '목록 거르기' })).not.toBeInTheDocument();
  });
});

describe('목록에 실을 값', () => {
  const base = me(ADULT, { show_adult_content: true, orientation: 'all' }) as unknown as Me;

  it('거르지 않으면 싣지 않는다', () => {
    expect(preferencesFor(undefined)).toEqual({});
    expect(preferencesFor(base)).toEqual({});
  });

  it('성인 확인을 하고 표시를 껐을 때만 숨기라고 싣는다', () => {
    expect(preferencesFor({ ...base, content_settings: { show_adult_content: false, orientation: 'all' } })).toEqual({ hide_adult: 'true' });
    expect(preferencesFor({ ...base, identity: UNVERIFIED, content_settings: { show_adult_content: false, orientation: 'all' } } as Me)).toEqual({});
  });

  it('성향은 전체가 아니면 싣는다', () => {
    expect(preferencesFor({ ...base, content_settings: { show_adult_content: true, orientation: 'male' } })).toEqual({ orientation: 'male' });
  });

  it('다시 읽는 것은 공개 목록뿐이다', () => {
    expect(isPublicListing({ queryKey: ['trpg', 'listings', 'browse'] })).toBe(true);
    expect(isPublicListing({ queryKey: ['chat', 'characters', 'public'] })).toBe(true);
    expect(isPublicListing({ queryKey: ['story', 'public-worlds', 'search'] })).toBe(true);
    expect(isPublicListing({ queryKey: ['trpg', 'banners', { signedIn: true }] })).toBe(true);
    expect(isPublicListing({ queryKey: ['asset', 'banners', { signedIn: true }] })).toBe(true);
    expect(isPublicListing({ queryKey: ['asset', 'admin', 'banners'] })).toBe(false);
    expect(isPublicListing({ queryKey: ['trpg', 'tables'] })).toBe(false);
    expect(isPublicListing({ queryKey: ['auth', 'me'] })).toBe(false);
  });
});
