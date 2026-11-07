// web/apps/web/src/pages/trpg/lobby/TableTabs.tsx
// 테이블 로비(B3)와 지나간 테이블(B10)의 위쪽 탭 줄(Stitch 13번). 지금 화면에 aria-current 를 단다.

import { NavLink } from 'react-router';

export function TableTabs() {
  return (
    <nav className="table-tabs" aria-label="테이블 화면">
      <NavLink to="/trpg/lobby" end>
        테이블 로비
      </NavLink>
      <NavLink to="/trpg/tables/past" end>
        지나간 테이블
      </NavLink>
    </nav>
  );
}
