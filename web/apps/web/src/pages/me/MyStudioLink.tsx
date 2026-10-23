// web/apps/web/src/pages/me/MyStudioLink.tsx
// 마이페이지의 "만들기". TRPG 의 제작 도구(B9)의 허브와 chat 의 캐릭터 만들기(C6), 캐릭터가 붙이는 chat 의 로어북으로 가는 길.

import { Link } from 'react-router';

export function MyStudioLink() {
  return (
    <section className="page-section" aria-labelledby="my-studio-heading">
      <h2 id="my-studio-heading">만들기</h2>
      <p>
        <Link to="/trpg/studio">재료와 시나리오 만들기(룰북, 세계관, 로어북, 몬스터 모음, 시나리오)</Link>
      </p>
      <p>
        <Link to="/chat/studio/characters">chat 캐릭터 만들기</Link>
      </p>
      <p>
        <Link to="/chat/studio/lorebooks">chat 로어북 만들기</Link>
      </p>
    </section>
  );
}
