// web/apps/web/src/pages/me/MySettingsLink.tsx
// 마이페이지의 "화면 설정". 이 브라우저에만 두는 설정(A12: 밝기, 글자 크기, 단축키)으로 가는 길.

import { Link } from 'react-router';

export function MySettingsLink() {
  return (
    <section className="page-section" aria-labelledby="my-settings-heading">
      <h2 id="my-settings-heading">화면 설정</h2>
      <p>
        <Link to="/settings">밝기, 글자 크기, 단축키</Link>
      </p>
    </section>
  );
}
