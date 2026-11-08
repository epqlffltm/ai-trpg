// web/apps/web/src/pages/me/MyAttendance.test.tsx
// 마이페이지 내 포인트 탭의 출석(Stitch 10번). 주기의 칸과 받기가 탭 안에 있고, 받으면 결과를 남기고,
// 보물 상자의 확률표는 접어 두었다가 펼치면 보이며, 출석 화면으로 가는 길이 있다. 읽지 못하면 알리고 다시 시도를 둔다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const ATTENDANCE = '/api/v1/auth/attendance';
const SILVER = ['140', '160', '180', '200', '220', '240', '260'];
const REWARDS = {
  cycle: SILVER.map((silver, index) => ({ day: index + 1, silver, chest: index === 6 })),
  chest: {
    table: 'v1',
    scale: 1000,
    expected_silver: '617',
    outcomes: [
      { outcome: 'mimic_bite', name: '미믹 — 물렸다', silver: '0', chance: 100, percent: '10%' },
      { outcome: 'dragon_hoard', name: '용의 보물', silver: '5000', chance: 30, percent: '3%' },
    ],
  },
};
const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: true, legal_adult: true, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
};
const TODAY = { today: '2026-10-24', verified: true, claimed: false, cycle_day: 3, cycle_length: 7, silver: '180', chest: false };

function signedIn(attendance: () => Response = () => json(200, TODAY)) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/billing/wallet/entries': () => json(200, { entries: [], next_before: null }),
    [`GET ${ATTENDANCE}/rewards`]: () => json(200, REWARDS),
    [`GET ${ATTENDANCE}`]: attendance,
    [`POST ${ATTENDANCE}`]: () => json(201, { day: '2026-10-24', cycle_day: 3, silver: '180', chest: null, badges: [] }),
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('내 포인트 탭의 출석', () => {
  it('주기의 칸과 받기가 탭 안에 있고, 받으면 결과를 남긴다. 확률표는 펼치면 보인다', async () => {
    signedIn();
    renderApp('/me?tab=points');

    const section = within(await screen.findByRole('region', { name: '출석체크로 실버 얻기' }));
    const cycle = within(await section.findByRole('list', { name: '출석 주기' }));
    expect(cycle.getAllByRole('listitem')).toHaveLength(7);
    expect(cycle.getByRole('listitem', { name: '3일째, 실버 180, 오늘' })).toBeInTheDocument();
    expect(section.getByRole('link', { name: '출석 화면' })).toHaveAttribute('href', '/wallet/attendance');

    await userEvent.click(section.getByRole('button', { name: '출석하기' }));
    expect(await section.findByText('받음: 실버 180 (3일째)')).toBeInTheDocument();

    const odds = section.getByText('출석 보물상자 획득 확률 안내').closest('details') as HTMLDetailsElement;
    expect(odds.open).toBe(false);
    await userEvent.click(within(odds).getByText('출석 보물상자 획득 확률 안내'));
    expect(odds.open).toBe(true);
    expect(within(odds).getByRole('row', { name: '용의 보물 5000 3%' })).toBeInTheDocument();
  });

  it('출석을 읽지 못하면 알리고 다시 시도를 둔다', async () => {
    let calls = 0;
    signedIn(() => {
      calls += 1;
      return calls === 1 ? json(500, { code: 'x', message: 'x' }) : json(200, TODAY);
    });
    renderApp('/me?tab=points');

    const section = within(await screen.findByRole('region', { name: '출석체크로 실버 얻기' }));
    await userEvent.click(await section.findByRole('button', { name: '다시 시도' }));
    expect(await section.findByRole('button', { name: '출석하기' })).toBeInTheDocument();
  });
});
