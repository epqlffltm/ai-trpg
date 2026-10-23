// web/apps/web/src/pages/me/MyStudioLink.tsx
// 마이페이지의 "만들기". 제작 도구(B9)로 가는 길. 지금은 룰북뿐이고, 재료와 시나리오 조립이 생기면 여기에 더한다.

import { Link } from 'react-router';

export function MyStudioLink() {
  return (
    <section className="page-section" aria-labelledby="my-studio-heading">
      <h2 id="my-studio-heading">만들기</h2>
      <p>
        <Link to="/trpg/studio/rulebooks">내 룰북</Link>
      </p>
    </section>
  );
}
