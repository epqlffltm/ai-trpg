// web/apps/web/src/layout/AppHeader.tsx
// 모든 화면의 위쪽 줄(Stitch 설계서의 [모든 화면의 틀]). 이름과 주 메뉴는 왼쪽 메뉴 열(AppSidebar)로 옮겼다.
// 왼쪽부터: 메뉴 열을 펴고 접는 ☰(넓은 화면), 이름(좁은 화면에만, 왼쪽 메뉴 열이 없어서), 작품 검색칸(#984),
// 오른쪽에 밝기 고르기(늘), 로그인했으면 성인 작품 표시(#986), 알림 종(A10, 펼치는 창), 프로필 단추(잔액과 MY 를 펼치는 창).
// 로그인 전이면 오른쪽은 밝기 고르기와 "로그인", "가입"뿐이다.
// 좁은 화면은 첫 줄에 이름, 알림 종, 프로필 단추(밝기와 성인 작품 표시는 숨긴다, 설정 화면에 있다), 둘째 줄에 검색칸이다.

import { Link, useLocation } from 'react-router';
import { useSession } from '../auth/useSession';
import { AccountMenu } from './AccountMenu';
import { HeaderAdultSwitch } from './HeaderAdultSwitch';
import { HeaderNotifications } from './HeaderNotifications';
import { HeaderSearch } from './HeaderSearch';
import { HeaderTheme } from './HeaderTheme';
import { SiteBrand } from './SiteBrand';
import type { Sidebar } from './useSidebar';

export function AppHeader({ sidebar }: { sidebar: Sidebar }) {
  const session = useSession();
  const location = useLocation();
  return (
    <header className="app-header">
      <button
        type="button"
        className="app-header__menu"
        aria-expanded={sidebar.open}
        aria-label={sidebar.open ? '사이트 메뉴 접기' : '사이트 메뉴 펼치기'}
        onClick={sidebar.toggle}
      >
        <span aria-hidden="true">☰</span>
      </button>
      <SiteBrand className="site-brand--compact" />
      <HeaderSearch />
      <div className="app-header__account">
        <HeaderTheme />
        {session ? (
          <>
            <HeaderAdultSwitch />
            <HeaderNotifications />
            <AccountMenu />
          </>
        ) : (
          <>
            <Link to="/login" state={{ from: location.pathname + location.search }}>
              로그인
            </Link>
            <Link to="/signup">가입</Link>
          </>
        )}
      </div>
    </header>
  );
}
