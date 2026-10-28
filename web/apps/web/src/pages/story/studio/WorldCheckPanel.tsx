// web/apps/web/src/pages/story/studio/WorldCheckPanel.tsx
// 세계관의 게시 점검(D7, GET /worlds/{id}/publish-check). 고치기의 옆에 늘 둔다. 저장할 때마다 다시 읽는다.
// 막는 것마다 글과 그 칸이 있는 탭으로 가는 단추(탭이 아직 없는 칸은 글만), 알리는 것(막지 않는다), 소개에서 걸러질 것.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { removedLine } from '../../chat/studio/characters/removedHtml';
import { worldProblemLine, worldWarningText } from './worldPublishText';
import { worldCheckQuery } from './worldQueries';
import { worldTabLabel, type WorldTab } from './worldTabs';

type Props = { worldId: string; goTo: (tab: WorldTab) => void };

export function WorldCheckPanel({ worldId, goTo }: Props) {
  const check = useQuery(worldCheckQuery(worldId));
  const data = check.data;
  return (
    <section className="scenario-check" aria-labelledby="world-check-heading">
      <h2 id="world-check-heading">게시 점검</h2>
      {check.isPending ? <p aria-busy="true">확인하는 중</p> : null}
      {check.isError ? (
        <Notice tone="error">
          확인하지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void check.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {data?.ready ? <p>지금 게시할 수 있습니다.</p> : null}
      {data && !data.ready ? (
        <>
          <p>게시하려면 고칠 것이 {data.problems.length}개 있습니다.</p>
          <ul className="plain-list" aria-label="고칠 것">
            {data.problems.map((name) => (
              <ProblemItem key={name} name={name} goTo={goTo} />
            ))}
          </ul>
        </>
      ) : null}
      {data && data.warnings.length > 0 ? (
        <>
          <p>게시는 되지만 알릴 것이 있습니다.</p>
          <ul className="plain-list" aria-label="알릴 것">
            {data.warnings.map((name) => (
              <li key={name} className="scenario-check__item">
                {worldWarningText(name)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {data && data.removed.length > 0 ? (
        <>
          <p>
            게시할 때 소개에서 걸러질 것이 {data.removed.length}개 있습니다.{' '}
            <Button variant="quiet" onClick={() => goTo('intro')}>
              소개 탭으로
            </Button>
          </p>
          <ul className="plain-list" aria-label="소개에서 걸러질 것">
            {data.removed.map((item, index) => (
              <li key={`${item.kind}-${item.name}-${index}`} className="scenario-check__item">
                {removedLine(item)}
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function ProblemItem({ name, goTo }: { name: string; goTo: (tab: WorldTab) => void }) {
  const line = worldProblemLine(name);
  const tab = line.tab;
  return (
    <li className="scenario-check__item">
      <span>{line.text}</span>{' '}
      {tab ? (
        <Button variant="quiet" onClick={() => goTo(tab)}>
          {worldTabLabel(tab)} 탭으로
        </Button>
      ) : null}
    </li>
  );
}
