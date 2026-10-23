// web/apps/web/src/pages/chat/studio/characters/CheckPanel.tsx
// 게시 점검(C6, GET /characters/{id}/publish-check). 캐릭터 고치기의 옆에 늘 둔다. 저장할 때마다 다시 읽는다.
// 문제마다 글과 그 칸이 있는 탭으로 가는 단추를 둔다. 모르는 문제는 이름만 적는다.
// 게시할 때 소개에서 걸러질 것(removed)도 보인다. 걸러져도 게시는 된다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { RemovedHtml } from '../../../../api/types';
import { checkQuery } from './characterQueries';
import { tabLabel, type CharacterTab } from './characterTabs';
import { problemLine } from './publishProblems';
import { removedLine } from './removedHtml';

type Props = { characterId: string; goTo: (tab: CharacterTab) => void };

export function CheckPanel({ characterId, goTo }: Props) {
  const check = useQuery(checkQuery(characterId));
  return (
    <section className="scenario-check" aria-labelledby="character-check-heading">
      <h2 id="character-check-heading">게시 점검</h2>
      {check.isPending ? <p aria-busy="true">확인하는 중</p> : null}
      {check.isError ? (
        <Notice tone="error">
          확인하지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void check.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {check.data?.ready ? <p>지금 게시할 수 있습니다.</p> : null}
      {check.data && !check.data.ready ? (
        <>
          <p>게시하려면 고칠 것이 {check.data.problems.length}개 있습니다.</p>
          <ul className="plain-list" aria-label="고칠 것">
            {check.data.problems.map((name) => (
              <ProblemItem key={name} name={name} goTo={goTo} />
            ))}
          </ul>
        </>
      ) : null}
      {check.data && check.data.removed.length > 0 ? <RemovedList removed={check.data.removed} goTo={goTo} /> : null}
    </section>
  );
}

function ProblemItem({ name, goTo }: { name: string; goTo: (tab: CharacterTab) => void }) {
  const line = problemLine(name);
  const section = line.section;
  return (
    <li className="scenario-check__item">
      <span>{line.text}</span>{' '}
      {section ? (
        <Button variant="quiet" onClick={() => goTo(section)}>
          {tabLabel(section)} 탭으로
        </Button>
      ) : null}
    </li>
  );
}

function RemovedList({ removed, goTo }: { removed: RemovedHtml[]; goTo: (tab: CharacterTab) => void }) {
  return (
    <>
      <p>
        게시할 때 소개에서 걸러질 것이 {removed.length}개 있습니다.{' '}
        <Button variant="quiet" onClick={() => goTo('intro')}>
          소개 탭으로
        </Button>
      </p>
      <ul className="plain-list" aria-label="소개에서 걸러질 것">
        {removed.map((item, index) => (
          <li key={`${item.kind}-${item.name}-${index}`} className="scenario-check__item">
            {removedLine(item)}
          </li>
        ))}
      </ul>
    </>
  );
}
