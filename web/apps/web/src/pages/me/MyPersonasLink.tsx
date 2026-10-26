// web/apps/web/src/pages/me/MyPersonasLink.tsx
// 마이페이지의 "내 페르소나". 대화에서 "나"의 설정(C4)으로 가는 길.

import { Link } from 'react-router';

export function MyPersonasLink() {
  return (
    <section className="page-section" aria-labelledby="my-personas-heading">
      <h2 id="my-personas-heading">페르소나</h2>
      <p>
        <Link to="/me/personas">내 페르소나</Link>
      </p>
    </section>
  );
}
