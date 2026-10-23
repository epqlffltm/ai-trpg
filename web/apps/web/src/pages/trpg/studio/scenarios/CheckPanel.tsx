// web/apps/web/src/pages/trpg/studio/scenarios/CheckPanel.tsx
// 게시 점검(B9, GET /scenarios/{id}/publish-check). 시나리오 고치기의 옆에 늘 둔다. 저장할 때마다 다시 읽는다.
// 문제마다 글과 그 칸이 있는 탭으로 가는 단추를 둔다. 아직 화면이 없는 묶음의 문제는 묶음의 이름만 적는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { problemLine } from './publishProblems';
import { publishCheckQuery } from './scenarioQueries';
import { isTab, sectionLabel, type ScenarioTab } from './scenarioTabs';

type Props = { scenarioId: string; goTo: (tab: ScenarioTab) => void };

export function CheckPanel({ scenarioId, goTo }: Props) {
  const check = useQuery(publishCheckQuery(scenarioId));
  return (
    <section className="scenario-check" aria-labelledby="scenario-check-heading">
      <h2 id="scenario-check-heading">게시 점검</h2>
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
          <ul className="plain-list scenario-check__list" aria-label="고칠 것">
            {check.data.problems.map((name) => (
              <ProblemItem key={name} name={name} goTo={goTo} />
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

function ProblemItem({ name, goTo }: { name: string; goTo: (tab: ScenarioTab) => void }) {
  const line = problemLine(name);
  const section = line.section;
  return (
    <li className="scenario-check__item">
      <span>{line.text}</span>{' '}
      {section && isTab(section) ? (
        <Button variant="quiet" onClick={() => goTo(section)}>
          {sectionLabel(section)} 탭으로
        </Button>
      ) : section ? (
        <span className="hint">({sectionLabel(section)}: 화면 준비 중)</span>
      ) : null}
    </li>
  );
}
