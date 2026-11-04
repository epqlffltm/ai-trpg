// web/apps/web/src/layout/AccountMenu.tsx
// 위쪽 줄의 프로필 단추와 펼쳐지는 메뉴(Stitch 설계서의 [모든 화면의 틀]). 로그인했을 때만 둔다(AppHeader).
// 단추에는 닉네임. 펼치면 위에 프로필(닉네임, 잔액과 "출석", "충전"), 그 아래 MY(마이페이지, 관심 작품, 페르소나, 갤러리, 설정),
// 운영자에게는 신고 처리(E4)와 홍보 배너(#994), 맨 아래 로그아웃. 길을 누르면 창을 닫는다.
// 로그아웃하면 읽어 둔 것(내 테이블, 내 대화)을 모두 버린다.
// 설계서의 팔로워·팔로잉 수, 성향 필터, 차단, 초대 코드, 활동 배지는 마이페이지와 설정에 있다(이 창에는 아직 두지 않는다).

import { Button } from '@ai-trpg/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { logout } from '../api/auth';
import { meQuery } from '../auth/queries';
import { isOperator } from '../auth/roles';
import { useSession } from '../auth/useSession';
import { HeaderBalance } from './HeaderBalance';
import { usePopover } from './usePopover';

/** MY 묶음의 길 */
const MY_LINKS: { to: string; label: string }[] = [
  { to: '/me', label: '마이페이지' },
  { to: '/me/hearts', label: '관심 작품' },
  { to: '/me/personas', label: '페르소나' },
  { to: '/gallery', label: '갤러리' },
  { to: '/settings', label: '설정' },
];

export function AccountMenu() {
  const me = useQuery(meQuery());
  const { open, toggle, close, ref } = usePopover();
  const nickname = me.data?.nickname || '내 정보';
  return (
    <div className="header-popover" ref={ref}>
      <button type="button" className="app-header__profile" aria-expanded={open} aria-label={`내 메뉴: ${nickname}`} onClick={toggle}>
        {nickname}
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
      </div>
      <ul className="plain-list profile-panel__links" aria-label="MY">
        {MY_LINKS.map((link) => (
          <li key={link.to}>
            <Link to={link.to} onClick={onClose}>
              {link.label}
            </Link>
          </li>
        ))}
      </ul>
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

/** 로그아웃. 서버가 거절해도(출처가 맞지 않음 등) 이 화면의 상태는 logout 이 이미 비웠다. 화면은 로그아웃한 것으로 돌아간다 */
function SignOutButton() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    await logout().catch(() => undefined);
    queryClient.clear();
    setBusy(false);
    void navigate('/', { replace: true });
  }

  return (
    <Button variant="quiet" busy={busy} onClick={() => void signOut()}>
      로그아웃
    </Button>
  );
}
