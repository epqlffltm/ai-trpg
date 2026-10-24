// web/apps/web/src/layout/AppHeader.tsx
// 모든 화면의 머리. 이름(첫 화면으로), 서비스, 내 정보 또는 로그인.
// 로그인했으면 알림(A10, 읽지 않은 수)과 잔액(A6, 지갑으로)도 둔다.

import { Link, useLocation } from 'react-router';
import { useSession } from '../auth/useSession';
import { AccountMenu } from './AccountMenu';
import { HeaderBalance } from './HeaderBalance';
import { HeaderNotifications } from './HeaderNotifications';

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
          <>
            <HeaderNotifications />
            <HeaderBalance />
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
