// web/apps/web/src/pages/me/MyPage.tsx
// 마이페이지(A5, Stitch 10번). 맨 위 프로필(MyProfileHead)과 탭 넷(?tab=). 고른 탭의 칸만 그린다(다른 탭의 서버는 부르지 않는다).
//   - 내 계정: 계정(본인인증 A3·보호자 동의 A4로 가는 길), 닉네임 바꾸기, 비밀번호 바꾸기, 모든 기기 로그아웃, 동의, 페르소나(C4), 갤러리(C7), 탈퇴
//   - 내 포인트: 지갑(A6)의 골드·실버 카드와 주문 내역(A8)으로 가는 길, 출석(주기의 칸, 오늘 받기, 보물 상자의 확률), 최근 사용 내역의 표
//   - 설정: 활동 배지(#193), 화면 설정(A12), 차단(#988), 관심 작품과 팔로잉(#989), 친구 초대(#990), 내 단축어(#981), 고객센터
//   - 제작자: 제작자 소개(#992), 만들기(B9 제작 도구 등)와 내 작품의 숫자(#991), 내 작품(종류마다의 목록, 공개 상태 칩)
// 로그인해야 열린다(App.tsx 의 RequireSession). 이 기기의 로그아웃은 머리에 있다.
// 주소에 #(칸의 제목 id)가 있으면 그 칸까지 내린다. 프로필 메뉴의 차단 관리, 팔로잉 제작자, 내 초대 코드, 활동 배지가 그렇게 온다.

import type { ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useHashScroll } from '../../hooks/useHashScroll';
import { AccountSummary } from './AccountSummary';
import { LogoutAllSection } from './LogoutAllSection';
import { MyAttendance } from './MyAttendance';
import { MyBadgesSection } from './MyBadgesSection';
import { MyBioSection } from './MyBioSection';
import { MyBlocksSection } from './MyBlocksSection';
import { MyConsents } from './MyConsents';
import { MyFollowingSection } from './MyFollowingSection';
import { MyGalleryLink } from './MyGalleryLink';
import { MyHeartsLink } from './MyHeartsLink';
import { MyInviteSection } from './MyInviteSection';
import { MyPersonasLink } from './MyPersonasLink';
import { MyProfileHead } from './MyProfileHead';
import { MyRecentEntries } from './MyRecentEntries';
import { MySettingsLink } from './MySettingsLink';
import { MyShortcutsLink } from './MyShortcutsLink';
import { MySupportLink } from './MySupportLink';
import { MyStudioLink } from './MyStudioLink';
import { MyWalletLink } from './MyWalletLink';
import { MY_TABS, myTabOf, myTabPath, type MyTab } from './myTabs';
import { NicknameChangeForm } from './NicknameChangeForm';
import { PasswordChangeForm } from './PasswordChangeForm';
import { WithdrawalSection } from './WithdrawalSection';
import { MyWorks } from './works/MyWorks';

export function MyPage() {
  const [params] = useSearchParams();
  const tab = myTabOf(params.get('tab'));
  useHashScroll();
  return (
    <main className="page page--medium my-page">
      <MyProfileHead />
      <MyTabs current={tab} />
      <div className="my-page__panel">{panelOf(tab)}</div>
    </main>
  );
}

/** 탭 줄. 탭마다 주소가 있어 다른 화면에서 그 탭으로 바로 온다 */
function MyTabs({ current }: { current: MyTab }) {
  return (
    <nav className="my-tabs" aria-label="마이페이지">
      {MY_TABS.map((tab) => (
        <Link key={tab.value} to={myTabPath(tab.value)} className="my-tab" aria-current={tab.value === current ? 'page' : undefined}>
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

function panelOf(tab: MyTab): ReactNode {
  if (tab === 'points') {
    return (
      <>
        <MyWalletLink />
        <MyAttendance />
        <MyRecentEntries />
      </>
    );
  }
  if (tab === 'settings') {
    return (
      <>
        <MyBadgesSection />
        <MySettingsLink />
        <MyBlocksSection />
        <MyHeartsLink />
        <MyFollowingSection />
        <MyInviteSection />
        <MyShortcutsLink />
        <MySupportLink />
      </>
    );
  }
  if (tab === 'creator') {
    return (
      <>
        <MyBioSection />
        <MyStudioLink />
        <MyWorks />
      </>
    );
  }
  return (
    <>
      <AccountSummary />
      <NicknameChangeForm />
      <PasswordChangeForm />
      <LogoutAllSection />
      <MyConsents />
      <MyPersonasLink />
      <MyGalleryLink />
      <WithdrawalSection />
    </>
  );
}
