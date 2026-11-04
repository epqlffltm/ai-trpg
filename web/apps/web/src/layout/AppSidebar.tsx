// web/apps/web/src/layout/AppSidebar.tsx
// 사이트의 왼쪽 메뉴 열(Stitch 설계서의 [모든 화면의 틀]). 넓은 화면에만 보인다(좁으면 아래 탭 바, MobileTabBar).
// 위에서 아래로: 이름(첫 화면으로), 큰 "만들기"(만들기 화면, 로그인 전이면 로그인으로), 주 메뉴, 맨 아래 공지.
// 최근 대화의 묶음과 이용 가이드·고객센터는 아직 없다(서버와 화면이 생기면 더한다).

import { Link, NavLink } from 'react-router';
import { SiteBrand } from './SiteBrand';

export function AppSidebar() {
  return (
    <aside className="app-sidebar" aria-label="사이트 메뉴">
      <SiteBrand />
      <Link to="/create" className="app-sidebar__create">
        만들기
      </Link>
      <nav aria-label="주 메뉴" className="app-sidebar__nav">
        <NavLink to="/" end>
          홈
        </NavLink>
        <NavLink to="/trpg">TRPG</NavLink>
        <NavLink to="/chat">chat</NavLink>
        <NavLink to="/story">story</NavLink>
        <NavLink to="/board">게시판</NavLink>
      </nav>
      <nav aria-label="안내" className="app-sidebar__footer">
        <Link to="/board/notice">공지</Link>
      </nav>
    </aside>
  );
}
