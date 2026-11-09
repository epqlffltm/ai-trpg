// web/apps/web/src/layout/AccountMenu.tsx
// 위쪽 줄의 프로필 단추와 펼쳐지는 메뉴(Stitch 설계서의 [모든 화면의 틀]). 로그인했을 때만 둔다(AppHeader).
// 단추에는 닉네임. 펼치면 위에 프로필(닉네임, 잔액과 "출석", "충전", 오늘 받았으면 "다음 출석까지 04:54:18"),
// 그 아래 맞춤 설정(성향 필터, 차단 관리), MY(마이페이지, 내 작품, 관심 작품, 팔로잉 제작자, 페르소나, 갤러리, 내 초대 코드, 활동 배지, 설정),
// 제작자 대시보드, 운영자에게는 신고 처리(E4)와 홍보 배너(#994), 맨 아래 로그아웃. 길과 차례는 accountMenuView.ts 에 있다. 길을 누르면 창을 닫는다.
// 성향 필터와 차단은 이 창에서 바꾸지 않고 그 칸(설정의 목록 거르기, 마이페이지의 차단)으로 간다.
// 로그아웃하면 읽어 둔 것(내 테이블, 내 대화)을 모두 버린다.
// 설계서의 팔로워·팔로잉 수는 서버가 내 수를 주지 않아 두지 않는다.
// 넓은 화면의 단추는 닉네임 글자, 좁은 화면은 닉네임의 첫 글자를 담은 동그라미다(설계서의 모바일 한 줄. 둘 가운데 하나를 app.css 가 숨긴다).

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { meQuery } from '../auth/queries';
import { isOperator } from '../auth/roles';
import { useSession } from '../auth/useSession';
import { useNow } from '../hooks/useNow';
import { attendanceQuery } from '../pages/attendance/attendanceQueries';
import { CREATOR_LINK, MY_LINKS, TUNE_LINKS, untilNextAttendance, type MenuLink } from './accountMenuView';
import { HeaderBalance } from './HeaderBalance';
import { SignOutButton } from './SignOutButton';
import { usePopover } from './usePopover';

export function AccountMenu() {
  const me = useQuery(meQuery());
  const { open, toggle, close, ref } = usePopover();
  const nickname = me.data?.nickname || '내 정보';
  return (
    <div className="header-popover" ref={ref}>
      <button type="button" className="app-header__profile" aria-expanded={open} aria-label={`내 메뉴: ${nickname}`} onClick={toggle}>
        <span className="app-header__avatar" aria-hidden="true">
          {Array.from(nickname)[0]}
        </span>
        <span className="app-header__label">{nickname}</span>
      </button>
      {open ? <ProfilePanel nickname={nickname} onClose={close} /> : null}
    </div>
  );
}

function ProfilePanel({ nickname, onClose }: { nickname: string; onClose: () => void }) {
  const operator = isOperator(useSession());
  return (
    <nav className="header-popover__panel profile-panel" aria-label="내 메뉴">
      <div className="profile-panel__card">
        <strong>{nickname}</strong>
        <span onClickCapture={onClose}>
          <HeaderBalance />
        </span>
        <div className="profile-panel__actions">
          <Link to="/wallet/attendance" onClick={onClose}>
            출석
          </Link>
          <Link to="/wallet/charge" onClick={onClose}>
            충전
          </Link>
        </div>
        <NextAttendance />
      </div>
      <MenuLinks label="맞춤 설정" links={TUNE_LINKS} onClose={onClose} />
      <MenuLinks label="MY" links={MY_LINKS} onClose={onClose} />
      <MenuLinks label="제작자" links={[CREATOR_LINK]} onClose={onClose} />
      {operator ? (
        <ul className="plain-list profile-panel__links" aria-label="운영">
          <li>
            <Link to="/operator/reports" onClick={onClose}>
              신고 처리
            </Link>
          </li>
          <li>
            <Link to="/operator/banners" onClick={onClose}>
              배너
            </Link>
          </li>
        </ul>
      ) : null}
      <SignOutButton />
    </nav>
  );
}

/** 묶음 하나의 길들 */
function MenuLinks({ label, links, onClose }: { label: string; links: MenuLink[]; onClose: () => void }) {
  return (
    <ul className="plain-list profile-panel__links" aria-label={label}>
      {links.map((link) => (
        <li key={link.label}>
          <Link to={link.to} onClick={onClose}>
            {link.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

/** 오늘 출석을 받았으면 다음 출석까지 남은 때. 받지 않았거나 읽지 못하면 없다 */
function NextAttendance() {
  const status = useQuery(attendanceQuery());
  const claimed = status.data?.claimed === true;
  const now = useNow(1000, claimed);
  const left = claimed && status.data ? untilNextAttendance(status.data.today, now) : null;
  return left ? <span className="hint">다음 출석까지 {left}</span> : null;
}
