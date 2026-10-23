// web/apps/web/src/pages/me/MyStudioLink.tsx
// 마이페이지의 "만들기". 제작 도구(B9)의 허브로 가는 길. 재료마다의 목록은 허브에 있다.

import { Link } from 'react-router';

export function MyStudioLink() {
  return (
    <section className="page-section" aria-labelledby="my-studio-heading">
      <h2 id="my-studio-heading">만들기</h2>
      <p>
        <Link to="/trpg/studio">재료와 시나리오 만들기(룰북, 세계관, 로어북, 몬스터 모음, 시나리오)</Link>
      </p>
    </section>
  );
}
