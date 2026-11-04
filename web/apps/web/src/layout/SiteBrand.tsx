// web/apps/web/src/layout/SiteBrand.tsx
// 사이트의 이름 "이매망량의 서재"와 낙관 모양의 표식. 누르면 첫 화면이다. 왼쪽 메뉴 열과 좁은 화면의 위쪽 줄이 함께 쓴다.

import { Link } from 'react-router';

export function SiteBrand({ className = '' }: { className?: string }) {
  return (
    <Link to="/" className={`site-brand ${className}`.trim()}>
      <span className="site-brand__mark" aria-hidden="true">
        書
      </span>
      이매망량의 서재
    </Link>
  );
}
