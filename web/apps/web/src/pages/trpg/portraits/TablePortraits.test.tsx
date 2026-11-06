// web/apps/web/src/pages/trpg/portraits/TablePortraits.test.tsx
// 테이블 방과 공개 소개의 캐릭터 그림(#983). 고른 프리젠의 그림을 이름 앞에 동그랗게 보이고 누르면 크게 본다.
// 그림이 없는 캐릭터는 이름의 첫 글자다. 공개 소개의 프리젠 그림은 로그인하지 않아도 받는다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, sheet, tableDetail } from '../../../test/tableFixtures';
import { initialOf } from './CharacterAvatar';

const TABLE_ID = '00000000-0000-4000-8000-0000000000c7';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;
const SCENARIO_ID = '00000000-0000-4000-8000-0000000000a1';
const FACE = '00000000-0000-4000-8000-0000000000f1';

function playing() {
  return tableDetail(TABLE_ID, {
    status: 'playing',
    members: [
      member(OTHER, { character: { name: '미아', description: '' }, sheet: sheet() }),
      member(ME, { is_host: true, character: { name: '렌', description: '' }, sheet: sheet(), portrait_id: FACE }),
    ],
  });
}

beforeEach(() => {
  // jsdom 에는 blob: 주소를 만드는 함수가 없다
  Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:face'), revokeObjectURL: vi.fn() });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('테이블 방의 캐릭터 그림', () => {
  it('내 캐릭터 카드의 이름 앞에 그림이 보이고 누르면 크게 본다. 그림이 없는 동료는 첫 글자다', async () => {
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
      ...roomRoutes(TABLE_ID, {
        [`GET ${BASE}`]: () => json(200, playing()),
        [`GET ${BASE}/portraits/${FACE}/image`]: () => new Response('png', { status: 200 }),
      }),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const status = within(await screen.findByRole('region', { name: '상태' }));
    await userEvent.click(await status.findByRole('button', { name: '렌의 그림 크게 보기' }));
    const dialog = within(await screen.findByRole('dialog', { name: '렌의 그림' }));
    expect(dialog.getByRole('img', { name: '렌의 그림' })).toHaveAttribute('src', 'blob:face');
    expect(seen.find((request) => request.url.endsWith(`/portraits/${FACE}/image`))?.headers.get('Authorization')).toBe('Bearer a1');
    await userEvent.click(dialog.getByRole('button', { name: '닫기' }));

    await userEvent.click(status.getByRole('button', { name: /일행·기록/ }));
    const card = (await status.findByText('미아')).closest('li') as HTMLElement;
    expect(within(card).getByText('미')).toHaveAttribute('aria-hidden', 'true');
  });
});

describe('공개 소개의 프리젠 그림', () => {
  it('로그인하지 않아도 프리젠의 그림을 받아 이름 앞에 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}`]: () =>
        json(200, {
          scenario_id: SCENARIO_ID,
          creator_id: OTHER,
          title: '잿빛 수도원',
          tagline: '',
          description: '',
          genre: 'fantasy',
          tags: [],
          rating: 'all',
          recommended_players: { min: 1, max: 4 },
          version: 1,
          version_note: '',
          published_at: '2026-11-01T00:00:00Z',
          heart_count: 0,
          start_count: 0,
          openings: ['문 앞에서 시작한다.'],
          character_modes: ['pregen'],
          pregens: [{ name: '수도사 렌', description: '', sheet: { max_hp: 12, abilities: {} }, portrait_id: FACE }],
          abilities: [],
          recommended_narration_model: null,
          references_allowed: false,
        }),
      'GET /api/v1/auth/public-names': () => json(200, { names: [] }),
      [`GET /api/v1/game/listings/${SCENARIO_ID}/portraits/${FACE}/image`]: () => new Response('png', { status: 200 }),
    });
    renderApp(`/trpg/scenarios/${SCENARIO_ID}`);

    expect(await screen.findByRole('img', { name: '수도사 렌의 그림' })).toHaveAttribute('src', 'blob:face');
  });
});

describe('첫 글자', () => {
  it('앞뒤 공백을 떼고 첫 글자, 비면 빈 글자', () => {
    expect(initialOf('  렌 ')).toBe('렌');
    expect(initialOf('')).toBe('');
  });
});
