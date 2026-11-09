// web/apps/web/src/layout/AppLayout.tsx
// 모든 화면의 틀(Stitch 설계서의 [모든 화면의 틀]). 넓은 화면은 왼쪽 메뉴 열 + 위쪽 줄 + 본문, 좁은 화면은 위쪽 줄 + 본문 + 맨 아래 탭 바다.
// 왼쪽 메뉴 열은 ☰ 로 접고 편다. 플레이 화면은 접은 채로 시작한다(useSidebar). 넓고 좁음은 CSS 가 가른다.
// 처음 열 때 로그인을 되살리는 동안(refresh)은 화면을 그리지 않는다. 짧고, 그리면 로그인 전의 목록을 한 번 더 부르게 된다.
// 다시 동의하거나 탈퇴를 기다리는 중이면(토큰이 인증 서버에만 통한다) 이 틀 대신 로고와 로그아웃만 있는 틀(LimitedLayout)을 그린다.
// 로그인, 가입, 비밀번호의 화면은 막지 않는다(재설정 메일의 링크 같은 것).
// 경로의 화면은 처음 갈 때 받을 수 있다(routing/pages.ts). 받는 동안은 "불러오는 중", 받지 못하거나 깨지면 RouteBoundary 의 안내다.
// 점검 중이면(어느 요청이 프록시의 점검 503 을 받으면) 틀 대신 점검 화면을, 처음 열 때 로그인을 되살리지 못하면(서버에 닿지 못함, 5xx)
// 장애 화면을 그린다(ServiceScreens). 둘 다 틀 없이 로고만 있다.

import { Suspense } from 'react';
import { Outlet, useLocation } from 'react-router';
import { isLimited } from '../api/session';
import { isAuthPath } from '../auth/safeReturnPath';
import { useBootSession } from '../auth/useBootSession';
import { useSession } from '../auth/useSession';
import { useMaintenance } from '../hooks/useMaintenance';
import { RouteBoundary } from '../routing/RouteBoundary';
import { AppHeader } from './AppHeader';
import { AppSidebar } from './AppSidebar';
import { LimitedLayout } from './LimitedLayout';
import { ListingPreferencesSync } from './ListingPreferencesSync';
import { MobileTabBar } from './MobileTabBar';
import { MaintenanceScreen, OutageScreen } from './ServiceScreens';
import { useSidebar } from './useSidebar';

export function AppLayout() {
  const boot = useBootSession();
  const maintenance = useMaintenance();
  const session = useSession();
  const { pathname } = useLocation();
  const sidebar = useSidebar(pathname);
  if (maintenance) return <MaintenanceScreen maintenance={maintenance} />;
  if (boot.state === 'unavailable') return <OutageScreen error={boot.error} onRetry={boot.retry} />;
  if (boot.state !== 'checking' && session && isLimited(session) && !isAuthPath(pathname)) return <LimitedLayout session={session} />;
  return (
    <div className="app-shell" data-sidebar={sidebar.open ? 'open' : 'closed'}>
      {sidebar.open ? <AppSidebar /> : null}
      <div className="app-shell__main">
        <AppHeader sidebar={sidebar} />
        <ListingPreferencesSync />
        {boot.state === 'checking' ? <p className="page page--loading">불러오는 중</p> : <RouteContent />}
      </div>
      <MobileTabBar />
    </div>
  );
}

function RouteContent() {
  const { pathname } = useLocation();
  return (
    <RouteBoundary resetKey={pathname}>
      <Suspense fallback={<p className="page page--loading">불러오는 중</p>}>
        <Outlet />
      </Suspense>
    </RouteBoundary>
  );
}
