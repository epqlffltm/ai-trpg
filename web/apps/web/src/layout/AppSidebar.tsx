// web/apps/web/src/layout/AppSidebar.tsx
// 사이트의 왼쪽 메뉴 열. 넓은 화면에만 보인다(좁으면 아래 탭 바, MobileTabBar).
// 위에서 아래로: 이름(첫 화면으로), 큰 "+ 만들기"(만들기 화면, 로그인 전이면 로그인으로), 주 메뉴 셋(홈, 내 채팅, 게시판),
// 최근 대화(SidebarRecent, 세 서비스를 섞은 한 목록), 맨 아래 한 줄의 공지사항 · 이용 가이드(/guide) · 고객센터(/support).
// TRPG·캐릭터·스토리는 메뉴로 나누지 않는다. 첫 화면과 검색에서 고른다.

import { Link, NavLink } from 'react-router';
import { SidebarRecent } from './SidebarRecent';
import { SiteBrand } from './SiteBrand';

export function AppSidebar() {
  return (
    <aside className="app-sidebar" aria-label="사이트 메뉴">
      <SiteBrand />
      <Link to="/create" className="app-sidebar__create">
        + 만들기
      </Link>
      <nav aria-label="주 메뉴" className="app-sidebar__nav">
        <NavLink to="/" end>
          홈
        </NavLink>
        <NavLink to="/conversations">내 채팅</NavLink>
        <NavLink to="/board">게시판</NavLink>
      </nav>
      <SidebarRecent />
      <nav aria-label="안내" className="app-sidebar__footer">
        <Link to="/board/notice">공지사항</Link>
        <span aria-hidden="true">·</span>
        <Link to="/guide">이용 가이드</Link>
        <span aria-hidden="true">·</span>
        <Link to="/support">고객센터</Link>
      </nav>
    </aside>
  );
}
