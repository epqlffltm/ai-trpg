// web/apps/web/src/pages/NotFoundPage.tsx
// 이 앱에 없는 경로. 프록시는 /api/ 가 아닌 주소를 모두 index.html 로 돌리므로 없는 경로는 여기서 알린다.
// 모양은 Stitch 8번의 찾을 수 없음: 사이트의 틀 안 가운데에 펼친 빈 책 그림, 큰 "404", 제목, 한 줄, 단추 "첫 화면으로".
// 운영자 화면에 권한 없이 왔을 때(RequireOperator)도 이 화면이다(있는지조차 알리지 않는다).

import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <main className="page page--narrow not-found">
      <EmptyBookArt />
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

/** 펼친 빈 책. 꾸밈이라 읽는 프로그램에는 숨긴다. 선 색은 글자 색과 강조색을 따른다 */
function EmptyBookArt() {
  return (
    <svg className="not-found__art" viewBox="0 0 240 120" width="240" height="120" aria-hidden="true" focusable="false">
      <path className="not-found__page" d="M120 22C96 10 60 8 28 14V100C60 94 96 96 120 108Z" />
      <path className="not-found__page" d="M120 22C144 10 180 8 212 14V100C180 94 144 96 120 108Z" />
      <path className="not-found__rule" d="M44 34H104M44 46H104M44 58H92M136 34H196M136 46H196M136 58H184" />
      <path className="not-found__shelf" d="M8 114H232" />
    </svg>
  );
}
