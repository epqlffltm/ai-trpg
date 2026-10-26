// web/apps/web/src/pages/trpg/room/FriendlyFirePanel.test.tsx
// 동료 피해(#803). 앉은 사람 모두가 자기 동의를 바꾸고 동료마다 드는 정도를 보며, 방장은 테이블의 정도를 바꾼다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { ME, member, OTHER, roomRoutes, tableDetail } from '../../../test/tableFixtures';

const TABLE_ID = '00000000-0000-4000-8000-0000000000e7';
const BASE = `/api/v1/game/tables/${TABLE_ID}`;

function waiting(extra: Record<string, unknown> = {}, mine: Record<string, unknown> = {}, other: Record<string, unknown> = {}) {
  return tableDetail(TABLE_ID, {
    members: [
      member(ME, { is_host: true, character: { name: '렌', description: '' }, ...mine }),
      member(OTHER, { character: { name: '미아', description: '' }, ...other }),
    ],
    recommended_narration_style: 'classic',
    input_step: 0,
    output_step: 0,
    ...extra,
  });
}

function open(routes: Record<string, (request: SeenRequest) => Response> = {}, me = ME) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: me }),
    ...roomRoutes(TABLE_ID, {
      'GET /api/v1/game/tables/narration-models': () => json(200, { free: false, models: [] }),
      [`GET ${BASE}`]: () => json(200, waiting({ friendly_fire: 'full' }, {}, { friendly_fire: 'prank' })),
      ...routes,
    }),
  });
}

async function panel(title: string) {
  const summary = await screen.findByText(title, { selector: 'h2' });
  await userEvent.click(summary);
  return within(summary.closest('details') as HTMLElement);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('FriendlyFirePanel', () => {
  it('내 동의를 바꾸고, 동료마다 낮은 쪽이 보인다', async () => {
    const { seen } = open(
      {
        [`PUT ${BASE}/members/me/friendly-fire`]: () =>
          json(200, waiting({ friendly_fire: 'full' }, {}, { friendly_fire: 'full' })),
      },
      OTHER,
    );
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const fire = await panel('동료 피해');
    expect(fire.getByText(/테이블: 다 됨/)).toBeInTheDocument();
    // 렌은 받아들이지 않았다. 테이블이 다 됨이어도 끔이다
    expect(fire.getByRole('list', { name: '동료마다 지금 드는 정도' })).toHaveTextContent('렌: 끔');
    await userEvent.selectOptions(fire.getByLabelText('나를 겨누는 것 받아들이기'), 'full');

    await vi.waitFor(() =>
      expect(seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/members/me/friendly-fire`)[0]?.body).toEqual({
        friendly_fire: 'full',
      }),
    );
  });

  it('방장은 테이블의 정도를 바꾼다', async () => {
    const { seen } = open({
      [`PUT ${BASE}/friendly-fire`]: () => json(200, waiting({ friendly_fire: 'prank' })),
    });
    renderApp(`/trpg/tables/${TABLE_ID}`);

    const host = await panel('방장');
    await userEvent.selectOptions(host.getByLabelText('동료 피해'), 'prank');

    await vi.waitFor(() =>
      expect(seen.filter((request) => request.method === 'PUT' && request.url === `${BASE}/friendly-fire`)[0]?.body).toEqual({
        friendly_fire: 'prank',
      }),
    );
  });
});
