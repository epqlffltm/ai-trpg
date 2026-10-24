// web/apps/web/src/pages/attendance/Attendance.test.tsx
// 출석·보물 상자(A9). 지갑에서 출석으로 가기, 주기의 칸(받음, 오늘, 앞으로)과 오늘의 양, 받으면 결과와 잔액 다시 읽기,
// 마지막 날의 보물 상자, 본인인증 전이면 막기, 이미 받았으면(409) 다시 읽어 막기, 보물 상자의 확률표, 홈의 출석 알림. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import type { AttendanceStatus } from '../../api/types';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { describeClaimProblem } from './attendanceProblem';
import { cellLabel, chestLine, cycleCells, todayLine } from './attendanceView';

const BILLING = '/api/v1/billing';
const ATTENDANCE = `${BILLING}/attendance`;
const SILVER = ['140', '160', '180', '200', '220', '240', '260'];

const REWARDS = {
  cycle: SILVER.map((silver, index) => ({ day: index + 1, silver, chest: index === 6 })),
  chest: {
    table: 'v1',
    scale: 1000,
    expected_silver: '617',
    outcomes: [
      { outcome: 'mimic_bite', name: '미믹 — 물렸다', silver: '0', chance: 100, percent: '10.0' },
      { outcome: 'goblin_pouch', name: '고블린의 주머니', silver: '300', chance: 300, percent: '30.0' },
      { outcome: 'dragon_hoard', name: '용의 보물', silver: '5000', chance: 30, percent: '3.0' },
    ],
  },
};

function today(extra: Partial<AttendanceStatus> = {}): AttendanceStatus {
  return { today: '2026-10-24', verified: true, claimed: false, cycle_day: 3, cycle_length: 7, silver: '180', chest: false, ...extra };
}

function signedIn(start: AttendanceStatus, claim: (request: SeenRequest) => Response) {
  let current = start;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, { nickname: '모험가', public_id: ME }),
    [`GET ${BILLING}/wallet`]: () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${BILLING}/wallet/entries`]: () => json(200, { entries: [], next_before: null }),
    [`GET ${ATTENDANCE}/rewards`]: () => json(200, REWARDS),
    [`GET ${ATTENDANCE}`]: () => json(200, current),
    [`POST ${ATTENDANCE}`]: (request) => {
      const answer = claim(request);
      if (answer.status < 400 || answer.status === 409) current = { ...current, claimed: true };
      return answer;
    },
  });
}

function count(seen: SeenRequest[], method: string, url: string): number {
  return seen.filter((request) => request.method === method && request.url === url).length;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('출석', () => {
  it('지갑에서 출석으로 간다. 주기의 칸과 오늘의 양을 보이고, 받으면 결과를 남기고 잔액을 다시 읽는다', async () => {
    const claimed = { day: '2026-10-24', cycle_day: 3, silver: '180', chest: null, expires_at: '2026-11-23T00:00:00+09:00' };
    const { seen } = signedIn(today(), () => json(201, claimed));
    renderApp('/wallet');

    await userEvent.click(await screen.findByRole('link', { name: '출석' }));
    const cycle = within(await screen.findByRole('list', { name: '출석 주기' }));
    expect(cycle.getAllByRole('listitem')).toHaveLength(7);
    expect(cycle.getByRole('listitem', { name: '2일째, 실버 160, 받음' })).toBeInTheDocument();
    expect(cycle.getByRole('listitem', { name: '3일째, 실버 180, 오늘' })).toBeInTheDocument();
    expect(cycle.getByRole('listitem', { name: '7일째, 실버 260, 보물 상자, 앞으로' })).toBeInTheDocument();
    expect(screen.getByText('오늘은 3일째 · 실버 180')).toBeInTheDocument();
    const walletReads = count(seen, 'GET', `${BILLING}/wallet`);

    await userEvent.click(screen.getByRole('button', { name: '출석하기' }));
    expect(await screen.findByText('받음: 실버 180 (3일째)')).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '오늘은 받았습니다' })).toBeDisabled();
    expect(screen.getByText('오늘은 3일째 · 실버 180 · 받았습니다. 내일 다시 오세요.')).toBeInTheDocument();
    await vi.waitFor(() => expect(count(seen, 'GET', `${BILLING}/wallet`)).toBeGreaterThan(walletReads));
  });

  it('마지막 날에는 출석하고 상자를 열어 그 결과와 확률표의 판을 보인다. 확률표를 공개한다', async () => {
    const chest = { table: 'v1', outcome: 'goblin_pouch', name: '고블린의 주머니', silver: '300' };
    signedIn(today({ cycle_day: 7, silver: '260', chest: true }), () => json(201, { day: '2026-10-24', cycle_day: 7, silver: '260', chest, expires_at: '2026-11-23T00:00:00+09:00' }));
    renderApp('/wallet/attendance');

    await userEvent.click(await screen.findByRole('button', { name: '출석하고 상자 열기' }));
    expect(await screen.findByText('보물 상자: 고블린의 주머니 · 실버 300 (확률표 v1)')).toBeInTheDocument();
    const odds = within(screen.getByRole('region', { name: '보물 상자의 확률' }));
    expect(odds.getByText(/확률표 v1 · 평균 실버 617/)).toBeInTheDocument();
    expect(odds.getByRole('row', { name: '용의 보물 5000 3.0%' })).toBeInTheDocument();
  });

  it('본인인증 전이면 받기를 막고 까닭을 적는다', async () => {
    signedIn(today({ verified: false }), () => json(403, { code: 'attendance.verification_required', message: 'x' }));
    renderApp('/wallet/attendance');
    expect(await screen.findByRole('button', { name: '출석하기' })).toBeDisabled();
    expect(screen.getByText(/본인인증을 마친 계정만 출석 보상을 받습니다/)).toBeInTheDocument();
  });

  it('이미 받았다는 답이 오면 까닭을 적고 단추를 막는다', async () => {
    signedIn(today(), () => json(409, { code: 'attendance.already_claimed', message: 'x' }));
    renderApp('/wallet/attendance');
    await userEvent.click(await screen.findByRole('button', { name: '출석하기' }));
    expect(await screen.findByText(/오늘은 이미 받았습니다/)).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: '오늘은 받았습니다' })).toBeDisabled();
  });
});

describe('홈의 출석 알림', () => {
  it('본인인증을 마쳤고 오늘 아직 받지 않았으면 홈에 한 줄과 출석으로 가는 길을 보인다', async () => {
    signedIn(today({ cycle_day: 7, silver: '260', chest: true }), () => json(201, {}));
    renderApp('/');
    expect(await screen.findByText(/오늘의 출석을 아직 받지 않았습니다. 오늘은 7일째 · 실버 260 · 보물 상자를 엽니다/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('link', { name: '출석하러 가기' }));
    expect(await screen.findByRole('button', { name: '출석하고 상자 열기' })).toBeInTheDocument();
  });

  it('이미 받았거나 본인인증 전이면 보이지 않는다', async () => {
    signedIn(today({ claimed: true }), () => json(201, {}));
    renderApp('/');
    expect(await screen.findByRole('heading', { name: 'TRPG 이어하기' })).toBeInTheDocument();
    expect(screen.queryByText(/오늘의 출석을 아직 받지 않았습니다/)).toBeNull();
  });
});

describe('출석의 순수한 함수', () => {
  it('칸의 상태는 cycle_day 와 받았는지로 정한다. 빠지면 1일째부터', () => {
    const states = (status: AttendanceStatus) => cycleCells(REWARDS.cycle, status).map((cell) => cell.state);
    expect(states(today())).toEqual(['done', 'done', 'today', 'later', 'later', 'later', 'later']);
    expect(states(today({ claimed: true }))).toEqual(['done', 'done', 'claimed', 'later', 'later', 'later', 'later']);
    expect(states(today({ cycle_day: 1 }))[0]).toBe('today');
    expect(cellLabel({ day: 7, silver: '260', chest: true, state: 'claimed' })).toBe('7일째, 실버 260, 보물 상자, 오늘 받음');
    expect(todayLine(today({ cycle_day: 7, silver: '260', chest: true }))).toBe('오늘은 7일째 · 실버 260 · 보물 상자를 엽니다');
    expect(chestLine({ day: '', cycle_day: 3, silver: '180', chest: null, expires_at: '' })).toBeNull();
  });

  it('받기의 실패: 409 는 이미 받음, 403 은 본인인증, 503 은 잠시 뒤', () => {
    expect(describeClaimProblem(new ApiError({ status: 409, detail: 'x', code: 'attendance.already_claimed' })).alreadyClaimed).toBe(true);
    expect(describeClaimProblem(new ApiError({ status: 403, detail: 'x', code: 'attendance.verification_required' })).message).toContain('본인인증');
    expect(describeClaimProblem(new ApiError({ status: 503, detail: 'x', retryAfter: 5 })).message).toContain('5초 뒤에');
  });
});
