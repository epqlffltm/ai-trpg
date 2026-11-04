// web/apps/web/src/pages/me/MyHeartsLink.tsx
// 마이페이지의 "관심 작품"(#989). 관심(하트)을 둔 시나리오, 캐릭터, 세계관을 모아 보는 화면(/me/hearts)으로 가는 길.

import { Link } from 'react-router';

export function MyHeartsLink() {
  return (
    <section className="page-section" aria-labelledby="my-hearts-heading">
      <h2 id="my-hearts-heading">관심 작품</h2>
      <p>
        <Link to="/me/hearts">관심을 둔 작품 보기</Link>
      </p>
    </section>
  );
}
