// web/apps/web/src/pages/trpg/lobby/TableTabs.test.tsx
// 로비와 지나간 테이블의 탭 줄(Stitch 13번), 테이블 만들기의 요약 줄(Stitch 14번). 지금 화면의 탭에 aria-current.

import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, expect, it } from 'vitest';
import { summaryRows } from '../tables/TableCreateForm';
import { TableTabs } from './TableTabs';

function tabsAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <TableTabs />
    </MemoryRouter>,
  );
  return within(screen.getByRole('navigation', { name: '테이블 화면' }));
}

describe('테이블 화면의 탭 줄', () => {
  it('로비에서는 로비가, 지나간 테이블에서는 지나간 테이블이 지금 화면이다', () => {
    const lobby = tabsAt('/trpg/lobby');
    expect(lobby.getByRole('link', { name: '테이블 로비' })).toHaveAttribute('aria-current', 'page');
    expect(lobby.getByRole('link', { name: '지나간 테이블' })).not.toHaveAttribute('aria-current');
  });

  it('지나간 테이블의 하나를 읽는 중에는 어느 탭도 지금 화면이 아니다', () => {
    const past = tabsAt('/trpg/tables/past/t-1');
    expect(past.getByRole('link', { name: '지나간 테이블' })).not.toHaveAttribute('aria-current');
  });
});

describe('테이블 만들기의 요약', () => {
  it('시나리오, 정원, 로비에 보이기와 비밀번호', () => {
    expect(summaryRows({ title: '잿빛 수도원' }, { capacity: 4, isPublic: true, password: '' })).toEqual([
      ['시나리오', '잿빛 수도원'],
      ['정원', '4명'],
      ['로비에 보이기', '보임'],
    ]);
    expect(summaryRows({ title: '잿빛 수도원' }, { capacity: 1, isPublic: true, password: 'x' })[1]).toEqual(['정원', '혼자']);
    expect(summaryRows({ title: '잿빛 수도원' }, { capacity: 2, isPublic: true, password: 'x' })[2]).toEqual(['로비에 보이기', '보임 · 비밀번호']);
    expect(summaryRows({ title: '잿빛 수도원' }, { capacity: 2, isPublic: false, password: '' })[2]).toEqual(['로비에 보이기', '보이지 않음(초대 코드로만)']);
  });
});
