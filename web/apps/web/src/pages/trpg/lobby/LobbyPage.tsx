// web/apps/web/src/pages/trpg/lobby/LobbyPage.tsx
// 테이블 로비(B3, /trpg/lobby). 들어갈 테이블을 찾는다. 공개 테이블에 들어가거나, 초대 코드로 들어가거나, 내 테이블로 돌아간다.
// 로그인해야 열린다. ?scenario_id= 가 있으면 그 시나리오의 테이블만 보인다(B2 의 "열린 테이블 보기").
// 넓으면 오른쪽에 내 테이블, 좁으면 아래에 둔다.

import { Link, useSearchParams } from 'react-router';
import { InviteJoinForm } from './InviteJoinForm';
import { LobbyList } from './LobbyList';
import { MyTablesAside } from './MyTablesAside';
import { ScenarioFilterNote } from './ScenarioFilterNote';

export function LobbyPage() {
  const [params, setParams] = useSearchParams();
  const scenarioId = params.get('scenario_id') || undefined;
  const createPath = scenarioId ? `/trpg/tables/new?${new URLSearchParams({ scenario_id: scenarioId })}` : '/trpg';
  return (
    <main className="page">
      <div className="page-head">
        <h1>테이블 로비</h1>
        <Link className="ui-button ui-button--primary" to={createPath}>
          {scenarioId ? '이 시나리오로 테이블 만들기' : '시나리오를 골라 테이블 만들기'}
        </Link>
      </div>
      <div className="lobby">
        <div className="lobby__main">
          {scenarioId ? <ScenarioFilterNote scenarioId={scenarioId} onClear={() => setParams({})} /> : null}
          <InviteJoinForm />
          <LobbyList scenarioId={scenarioId} createPath={createPath} />
        </div>
        <MyTablesAside />
      </div>
    </main>
  );
}
