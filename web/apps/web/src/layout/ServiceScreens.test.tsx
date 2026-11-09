// web/apps/web/src/layout/ServiceScreens.test.tsx
// 점검과 장애의 화면(Stitch 8번). 프록시가 점검의 503 을 답하면 틀 없이 점검 화면(시간, 글), 처음 열 때 서버에 닿지 못하면
// 장애 화면(요청 번호, 다시 시도)이고, 다시 시도해 닿으면 평소의 화면이다. 점검 시간의 한 줄(순수한 함수).

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import { resetMaintenance } from '../api/maintenance';
import { REFRESH_PATH } from '../api/refresh';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { renderApp } from '../test/renderApp';
import { maintenanceWindow } from './maintenanceView';

const MAINTENANCE = {
  detail: '서버를 옮기는 중입니다.',
  code: 'maintenance',
  starts_at: '2026-11-04T02:00:00+09:00',
  ends_at: '2026-11-04T04:00:00+09:00',
};

afterEach(() => {
  resetMaintenance();
});

describe('점검', () => {
  it('어느 요청이든 점검의 503 을 받으면 틀 없이 점검 화면이다. 시간과 점검 파일의 글이 보인다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(503, MAINTENANCE),
      'GET /api/v1/billing/wallet': () => json(503, MAINTENANCE),
    });
    renderApp('/settings');

    expect(await screen.findByRole('heading', { level: 1, name: '점검 중입니다' })).toBeInTheDocument();
    expect(screen.getByText('서버를 옮기는 중입니다.')).toBeInTheDocument();
    expect(screen.getByText(maintenanceWindow({ startsAt: MAINTENANCE.starts_at, endsAt: MAINTENANCE.ends_at }) as string)).toBeInTheDocument();
    expect(screen.getByText('남은 크레딧과 진행 중인 판은 안전하게 보관됩니다.')).toBeInTheDocument();
    expect(screen.queryByRole('complementary', { name: '사이트 메뉴' })).toBeNull();
    expect(screen.getByRole('link', { name: /이매망량의 서재/ })).toHaveAttribute('href', '/');
  });

  it('로그인을 되살리는 요청이 점검을 받아도 장애가 아니라 점검 화면이다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(503, { detail: '점검 중입니다.', code: 'maintenance' }) });
    renderApp('/');

    expect(await screen.findByRole('heading', { level: 1, name: '점검 중입니다' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '잠시 연결할 수 없습니다' })).toBeNull();
  });

  it('점검이 아닌 서버의 503 은 점검 화면이 아니다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
      'GET /api/v1/auth/me': () => json(503, { detail: '잠시 뒤에', code: 'billing.unavailable' }),
      'GET /api/v1/billing/wallet': () => json(503, { detail: '잠시 뒤에' }),
    });
    renderApp('/settings');

    expect(await screen.findByRole('heading', { level: 1, name: '설정' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '점검 중입니다' })).toBeNull();
  });
});

describe('장애', () => {
  it('처음 열 때 서버에 닿지 못하면 장애 화면과 요청 번호이고, 다시 시도해 닿으면 평소의 화면이다', async () => {
    let calls = 0;
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => {
        calls += 1;
        return calls === 1 ? json(502, { detail: '서버에 닿지 못했습니다.' }, { 'X-Request-ID': 'req-42' }) : json(401, { detail: 'no cookie' });
      },
    });
    renderApp('/settings');

    expect(await screen.findByRole('heading', { level: 1, name: '잠시 연결할 수 없습니다' })).toBeInTheDocument();
    expect(screen.getByText('계속되면 고객센터에 요청 번호를 알려 주세요: req-42')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '다시 시도' }));

    expect(await screen.findByRole('heading', { level: 1, name: '설정' })).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});

describe('점검 시간의 한 줄', () => {
  it('같은 날이면 끝은 시각만, 한쪽만 알면 부터·까지, 모르면 없다', () => {
    const same = maintenanceWindow({ startsAt: '2026-11-04T02:00:00Z', endsAt: '2026-11-04T04:00:00Z' }) as string;
    expect(same).toMatch(/2026년 11월 4일 .*2:00 ~ .*4:00$/);
    expect(same.split('2026').length).toBe(2);
    expect(maintenanceWindow({ startsAt: null, endsAt: '2026-11-04T04:00:00Z' })).toMatch(/까지$/);
    expect(maintenanceWindow({ startsAt: '2026-11-04T02:00:00Z', endsAt: null })).toMatch(/부터$/);
    expect(maintenanceWindow({ startsAt: null, endsAt: null })).toBeNull();
  });
});
