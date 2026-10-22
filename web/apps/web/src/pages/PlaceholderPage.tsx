// web/apps/web/src/pages/PlaceholderPage.tsx
// 아직 만들지 않은 서비스의 화면(TRPG 의 B1~B10, chat 의 C1~C7, story). 경로만 먼저 잡아 둔다.

import { Link } from 'react-router';

export function PlaceholderPage({ service }: { service: string }) {
  return (
    <main className="page page--narrow">
      <h1>{service}</h1>
      <p>이 화면은 준비 중입니다.</p>
      <Link to="/">첫 화면으로</Link>
    </main>
  );
}
