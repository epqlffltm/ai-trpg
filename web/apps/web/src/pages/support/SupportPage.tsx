// web/apps/web/src/pages/support/SupportPage.tsx
// 고객센터(/support). 왼쪽 메뉴 열 맨 아래의 "고객센터"에서 온다(Stitch 설계서의 [모든 화면의 틀]).
// 로그인하지 않아도 열린다(로그인이 안 되는 문의가 있다). 문의 보내기와, 로그인했으면 내 문의와 답.
// 문의는 인증 서버가 받고 운영자가 메일로 답한다. 시안에 이 화면은 따로 없어 다른 계정 화면(page-section)의 틀을 쓴다.

import { Link } from 'react-router';
import { useSession } from '../../auth/useSession';
import { InquiryForm } from './InquiryForm';
import { MyInquiries } from './MyInquiries';

export function SupportPage() {
  const signedIn = useSession() !== null;
  return (
    <main className="page page--medium">
      <h1>고객센터</h1>
      <p className="hint">
        궁금한 점이나 문제를 적어 보내 주세요. 운영자가 확인하고 메일로 답합니다. 먼저 <Link to="/guide">이용 가이드</Link>에서 답을 찾아볼 수 있습니다.
      </p>
      <section className="page-section" aria-labelledby="inquiry-form-heading">
        <h2 id="inquiry-form-heading">문의 보내기</h2>
        <InquiryForm signedIn={signedIn} />
      </section>
      {signedIn ? <MyInquiries /> : null}
    </main>
  );
}
