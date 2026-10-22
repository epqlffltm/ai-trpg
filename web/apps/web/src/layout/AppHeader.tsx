// web/apps/web/src/layout/AppHeader.tsx
// 모든 화면의 머리. 이름(첫 화면으로), 서비스, 내 정보 또는 로그인.
// 잔액(A6)과 알림 배지(A10)는 그 화면을 만들 때 더한다.

import { Link, useLocation } from 'react-router';
import { useSession } from '../auth/useSession';
import { AccountMenu } from './AccountMenu';

export function AppHeader() {
  const session = useSession();
  const location = useLocation();
  return (
    <header className="app-header">
      <Link to="/" className="app-header__brand">
        AI TRPG
      </Link>
      <nav aria-label="주 메뉴" className="app-header__nav">
        <Link to="/trpg">TRPG</Link>
        <Link to="/chat">chat</Link>
        <Link to="/story">story</Link>
      </nav>
      <div className="app-header__account">
        {session ? (
          <AccountMenu />
        ) : (
          <Link to="/login" state={{ from: location.pathname + location.search }}>
            로그인
          </Link>
        )}
      </div>
    </header>
  );
}
