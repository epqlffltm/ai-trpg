// web/apps/web/src/pages/NotFoundPage.tsx
// 이 앱에 없는 경로. 프록시는 /api/ 가 아닌 주소를 모두 index.html 로 돌리므로 없는 경로는 여기서 알린다.

import { Link } from 'react-router';

export function NotFoundPage() {
  return (
    <main className="page page--narrow">
      <h1>찾을 수 없습니다</h1>
      <p>주소가 바뀌었거나 없는 화면입니다.</p>
      <Link to="/">첫 화면으로</Link>
    </main>
  );
}
