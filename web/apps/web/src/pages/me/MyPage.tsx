// web/apps/web/src/pages/me/MyPage.tsx
// 마이페이지(A5). 계정, 지갑으로 가는 길(A6), 비밀번호 바꾸기, 모든 기기 로그아웃, 동의. 지갑 말고는 인증 서버만 부른다.
// 로그인해야 열린다(App.tsx 의 RequireSession). 이 기기의 로그아웃은 머리에 있다.
// 주문 내역, 본인인증(A3), 보호자 동의(A4), 탈퇴 요청은 그 화면을 만들 때 여기에 더한다.

import { AccountSummary } from './AccountSummary';
import { LogoutAllSection } from './LogoutAllSection';
import { MyConsents } from './MyConsents';
import { MyWalletLink } from './MyWalletLink';
import { PasswordChangeForm } from './PasswordChangeForm';

export function MyPage() {
  return (
    <main className="page page--medium">
      <h1>내 정보</h1>
      <AccountSummary />
      <MyWalletLink />
      <PasswordChangeForm />
      <LogoutAllSection />
      <MyConsents />
    </main>
  );
}
