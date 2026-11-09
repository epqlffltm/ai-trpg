// web/apps/web/src/pages/me/MySupportLink.tsx
// 마이페이지의 "고객센터". 문의 보내기와 내 문의(/support)로 가는 길. 좁은 화면에는 왼쪽 메뉴 열이 없어 여기서도 간다.

import { Link } from 'react-router';

export function MySupportLink() {
  return (
    <section className="page-section" aria-labelledby="my-support-heading">
      <h2 id="my-support-heading">고객센터</h2>
      <p>
        <Link to="/support">문의 보내기와 내 문의</Link>
      </p>
    </section>
  );
}
