// web/apps/web/src/pages/home/HomePage.tsx
// 첫 화면(A1, Stitch 2·3). 홍보 배너(#994), 본인인증 안내·출석 알림과 이어하기(로그인했을 때), 새로 공개된 것, 이번 주 인기(#985).
// 서비스로 가는 길은 왼쪽 메뉴 열과 아래 탭 바가 맡아 여기에는 따로 두지 않는다. 줄마다 가로로 넘긴다.
// 로그인하지 않아도 전체이용가의 목록까지 보이는 메인이다(2026-10-20 결정).
// 다시 동의하거나 탈퇴를 기다리는 중이면 이 화면 대신 그 화면이 뜬다(AppLayout 의 LimitedSessionGate).

import { Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import { useSession } from '../../auth/useSession';
import { AttendanceNotice } from './AttendanceNotice';
import { ContinueRows } from './ContinueRows';
import { IdentityNotice } from './IdentityNotice';
import { PromoBanner } from './PromoBanner';
import { PublicRows } from './PublicRows';
import { RankingRows } from './RankingRows';

export function HomePage() {
  const session = useSession();
  return (
    <main className="page">
      <h1 className="visually-hidden">이매망량의 서재</h1>
      <PromoBanner signedIn={session !== null} />
      {session ? <IdentityNotice /> : null}
      {session ? <AttendanceNotice /> : null}
      {session ? <ContinueRows /> : <SignInNotice />}
      <PublicRows signedIn={session !== null} />
      <RankingRows signedIn={session !== null} />
    </main>
  );
}

function SignInNotice() {
  return (
    <Notice>
      <Link to="/login">로그인</Link>하면 하던 테이블과 대화를 여기서 이어서 볼 수 있습니다.
    </Notice>
  );
}
