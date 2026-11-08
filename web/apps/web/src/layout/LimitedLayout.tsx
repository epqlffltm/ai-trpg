// web/apps/web/src/layout/LimitedLayout.tsx
// 다시 동의·탈퇴 유예의 틀(Stitch 설계서 7번). 토큰이 인증 서버에만 통하는 동안 모든 화면의 틀 대신 그린다(AppLayout).
// 왼쪽 메뉴 열, 검색칸, 알림 종, 프로필 메뉴, 맨 아래 탭 바가 없다. 위쪽 줄에는 이름(첫 화면으로)과 "로그아웃"만 있다.
// 다른 서버는 모두 401 이라 그 틀의 칸(잔액, 알림)을 부르지 않는 것이 맞다. 본문은 다시 동의나 탈퇴 유예다(LimitedSessionGate).

import type { Session } from '../api/session';
import { LimitedSessionGate } from '../pages/limited/LimitedSessionGate';
import { SignOutButton } from './SignOutButton';
import { SiteBrand } from './SiteBrand';

export function LimitedLayout({ session }: { session: Session }) {
  return (
    <div className="app-shell app-shell--limited">
      <div className="app-shell__main">
        <header className="app-header app-header--limited">
          <SiteBrand />
          <div className="app-header__account">
            <SignOutButton />
          </div>
        </header>
        <LimitedSessionGate session={session} />
      </div>
    </div>
  );
}
