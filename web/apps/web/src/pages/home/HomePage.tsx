// web/apps/web/src/pages/home/HomePage.tsx
// 첫 화면(A1). 서비스 고르기, 이어하기(로그인했을 때), 공개된 것.
// 로그인하지 않아도 전체이용가의 목록까지 보이는 메인이다(2026-10-20 결정).
// 다시 동의하거나 탈퇴를 기다리는 중이면 이 화면 대신 그 화면이 뜬다(AppLayout 의 LimitedSessionGate).

import { Notice } from '@ai-trpg/ui';
import { Link } from 'react-router';
import { useSession } from '../../auth/useSession';
import { ContinueRows } from './ContinueRows';
import { PublicRows } from './PublicRows';
import { ServicePicker } from './ServicePicker';

export function HomePage() {
  const session = useSession();
  return (
    <main className="page">
      <h1 className="visually-hidden">AI TRPG</h1>
      <ServicePicker />
      {session ? <ContinueRows /> : <SignInNotice />}
      <PublicRows signedIn={session !== null} />
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
