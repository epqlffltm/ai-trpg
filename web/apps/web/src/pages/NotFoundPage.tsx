// web/apps/web/src/pages/NotFoundPage.tsx
// 이 앱에 없는 경로. 프록시는 /api/ 가 아닌 주소를 모두 index.html 로 돌리므로 없는 경로는 여기서 알린다.
// 사이트의 틀 안 가운데에 둥근 네모 안의 책 그림, 큰 "404", 제목, 한 줄, 단추 "첫 화면으로".
// 운영자 화면에 권한 없이 왔을 때(RequireOperator)도 이 화면이다(있는지조차 알리지 않는다).

import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <main className="page page--narrow not-found">
      <span className="not-found__art" aria-hidden="true">
        <BookIcon />
      </span>
      <p className="not-found__code" aria-hidden="true">
        404
      </p>
      <h1>찾을 수 없습니다</h1>
      <p>주소가 바뀌었거나 없는 화면입니다.</p>
      <Link className="ui-button ui-button--primary" to="/">
        첫 화면으로
      </Link>
    </main>
  );
}

/** 펼친 책. 꾸밈이라 읽는 프로그램에는 숨긴다. 글자 크기를 따라가고 색은 강조색이다 */
function BookIcon() {
  return (
    <svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" focusable="false">
      <path d="M12 6C10 4.8 7 4.5 3 5v13c4-.5 7-.2 9 1 2-1.2 5-1.5 9-1V5c-4-.5-7-.2-9 1Z" />
      <path d="M12 6v13M15 9h3M15 12h3M15 15h2" />
    </svg>
  );
}
