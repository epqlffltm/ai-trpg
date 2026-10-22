// web/apps/web/src/layout/AppLayout.tsx
// 모든 화면의 틀. 머리 아래에 경로의 화면을 그린다.
// 처음 열 때 로그인을 되살리는 동안(refresh)은 화면을 그리지 않는다. 짧고, 그리면 로그인 전의 목록을 한 번 더 부르게 된다.
// 다시 동의하거나 탈퇴를 기다리는 중이면(토큰이 인증 서버에만 통한다) 경로의 화면 대신 그 화면을 그린다.
// 로그인, 가입, 비밀번호의 화면은 막지 않는다(재설정 메일의 링크 같은 것).

import { Notice } from '@ai-trpg/ui';
import { Outlet, useLocation } from 'react-router';
import { isLimited } from '../api/session';
import { isAuthPath } from '../auth/safeReturnPath';
import { useBootSession } from '../auth/useBootSession';
import { useSession } from '../auth/useSession';
import { LimitedSessionGate } from '../pages/limited/LimitedSessionGate';
import { AppHeader } from './AppHeader';

export function AppLayout() {
  const boot = useBootSession();
  return (
    <>
      <AppHeader />
      {boot === 'checking' ? (
        <p className="page page--loading">불러오는 중</p>
      ) : (
        <>
          {boot === 'unavailable' ? (
            <div className="page">
              <Notice>로그인 상태를 확인하지 못했습니다. 잠시 뒤에 새로 고쳐 보세요.</Notice>
            </div>
          ) : null}
          <RouteContent />
        </>
      )}
    </>
  );
}

function RouteContent() {
  const session = useSession();
  const { pathname } = useLocation();
  if (session && isLimited(session) && !isAuthPath(pathname)) return <LimitedSessionGate session={session} />;
  return <Outlet />;
}
