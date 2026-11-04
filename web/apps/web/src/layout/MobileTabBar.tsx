// web/apps/web/src/layout/MobileTabBar.tsx
// 좁은 화면의 맨 아래 탭 바(Stitch 설계서의 [모든 화면의 틀]). 홈, 탐색, 만들기(가운데), 대화, 마이 다섯 칸이다.
// 탐색은 TRPG·chat·story·게시판으로 가는 작은 창을 연다. 대화는 첫 화면의 이어하기(서비스마다)로 간다(최근 대화만 모은 화면은 아직 없다).
// 마이와 만들기는 로그인해야 열리는 화면이라, 로그인 전이면 그 화면이 로그인으로 보낸다.

import { useState } from 'react';
import { Link, NavLink } from 'react-router';

export function MobileTabBar() {
  const [exploring, setExploring] = useState(false);
  return (
    <nav aria-label="아래 메뉴" className="mobile-tab-bar">
      {exploring ? <ExploreSheet onClose={() => setExploring(false)} /> : null}
      <NavLink to="/" end className="mobile-tab-bar__item">
        홈
      </NavLink>
      <button
        type="button"
        className="mobile-tab-bar__item"
        aria-expanded={exploring}
        onClick={() => setExploring((before) => !before)}
      >
        탐색
      </button>
      <Link to="/create" className="mobile-tab-bar__item mobile-tab-bar__item--create">
        만들기
      </Link>
      <Link to="/" className="mobile-tab-bar__item">
        대화
      </Link>
      <NavLink to="/me" className="mobile-tab-bar__item">
        마이
      </NavLink>
    </nav>
  );
}

/** 탐색의 창에서 갈 곳 */
const EXPLORE: { to: string; label: string }[] = [
  { to: '/trpg', label: 'TRPG' },
  { to: '/chat', label: 'chat' },
  { to: '/story', label: 'story' },
  { to: '/board', label: '게시판' },
];

/** 탐색의 창. 고르면 닫힌다 */
function ExploreSheet({ onClose }: { onClose: () => void }) {
  return (
    <div className="mobile-tab-bar__sheet" role="group" aria-label="탐색">
      {EXPLORE.map(({ to, label }) => (
        <Link key={to} to={to} onClick={onClose}>
          {label}
        </Link>
      ))}
    </div>
  );
}
