// web/apps/web/src/pages/me/MyShortcutsLink.tsx
// 마이페이지의 "내 단축어"(#981). 대화와 이야기에서 "/이름"으로 부르는 글을 관리하는 화면으로 가는 길.

import { Link } from 'react-router';

export function MyShortcutsLink() {
  return (
    <section className="page-section" aria-labelledby="my-shortcuts-heading">
      <h2 id="my-shortcuts-heading">단축어</h2>
      <p>
        <Link to="/me/shortcuts">내 단축어</Link>
      </p>
    </section>
  );
}
