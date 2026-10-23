// web/apps/web/src/pages/trpg/studio/StudioPage.tsx
// 만들기(B9 제작 도구, /trpg/studio). 재료의 종류마다 목록으로 가는 길. 마이페이지(A5)의 "만들기"에서 온다.
// 재료(룰북, 세계관, 로어북, 몬스터 모음)를 만들고, 시나리오에서 모아 게시한다. 시나리오가 목록의 맨 끝이다.

import { Link } from 'react-router';
import { kindText, STUDIO_KINDS, studioPath } from './studioKinds';

export function StudioPage() {
  return (
    <main className="page page--medium">
      <h1>만들기</h1>
      <p className="hint">재료를 만들고 시나리오에서 모아 게시합니다. 재료는 나만 봅니다.</p>
      <ul className="plain-list studio-list" aria-label="만들 것">
        {STUDIO_KINDS.map((kind) => (
          <li key={kind} className="studio-list__item">
            <Link to={studioPath(kind)}>{kindText(kind).title}</Link>
            <p className="studio-list__description">{kindText(kind).intro}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}
