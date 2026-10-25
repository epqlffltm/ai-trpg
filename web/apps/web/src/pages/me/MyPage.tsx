// web/apps/web/src/pages/me/MyPage.tsx
// 마이페이지(A5). 계정, 지갑으로 가는 길(A6), 만들기(B9 제작 도구)와 갤러리(C7), 화면 설정(A12)으로 가는 길, 비밀번호 바꾸기, 모든 기기 로그아웃, 동의.
// 지갑 말고는 인증 서버만 부른다.
// 로그인해야 열린다(App.tsx 의 RequireSession). 이 기기의 로그아웃은 머리에 있다.
// 본인인증(A3)과 보호자 동의(A4)는 계정의 그 줄에서 간다. 탈퇴 요청은 그 화면을 만들 때 여기에 더한다.

import { AccountSummary } from './AccountSummary';
import { LogoutAllSection } from './LogoutAllSection';
import { MyConsents } from './MyConsents';
import { MyGalleryLink } from './MyGalleryLink';
import { MySettingsLink } from './MySettingsLink';
import { MyStudioLink } from './MyStudioLink';
import { MyWalletLink } from './MyWalletLink';
import { PasswordChangeForm } from './PasswordChangeForm';

export function MyPage() {
  return (
    <main className="page page--medium">
      <h1>내 정보</h1>
      <AccountSummary />
      <MyWalletLink />
      <MyStudioLink />
      <MyGalleryLink />
      <MySettingsLink />
      <PasswordChangeForm />
      <LogoutAllSection />
      <MyConsents />
    </main>
  );
}
