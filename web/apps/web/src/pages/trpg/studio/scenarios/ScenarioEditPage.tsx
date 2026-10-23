// web/apps/web/src/pages/trpg/studio/scenarios/ScenarioEditPage.tsx
// 시나리오 고치기(B9, /trpg/studio/scenarios/:scenarioId?tab=). 칸의 묶음마다 탭이 있고 탭마다 저장한다.
// 탭은 모두 그려 두고 고르지 않은 것을 숨긴다. 다른 탭에 갔다 와도 저장하지 않은 입력이 남는다.
// 옆(좁은 화면에서는 위)에 게시 점검을 늘 둔다. 문제를 누르면 그 탭으로 간다.

import { Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import type { ScenarioDetail } from '../../../../api/types';
import { AssetLoad } from '../AssetLoad';
import { kindText, studioPath } from '../studioKinds';
import { useSavedNotice } from '../useSavedNotice';
import { BasicsTab } from './BasicsTab';
import { CharactersTab } from './CharactersTab';
import { CheckPanel } from './CheckPanel';
import { ItemsTab } from './ItemsTab';
import { MapTab } from './MapTab';
import { MonstersTab } from './MonstersTab';
import { QuestsTab } from './QuestsTab';
import { NpcsTab } from './NpcsTab';
import { MaterialsTab } from './MaterialsTab';
import { OpeningsTab } from './OpeningsTab';
import { PublishTab } from './PublishTab';
import { scenarioQuery } from './scenarioQueries';
import { SCENARIO_TABS, sectionLabel, tabOf, type ScenarioTab } from './scenarioTabs';

export function ScenarioEditPage() {
  const { scenarioId = '' } = useParams();
  const query = useQuery(scenarioQuery(scenarioId));
  return (
    <main className="page">
      <p>
        <Link to={studioPath('scenarios')}>{kindText('scenarios').title}</Link>
      </p>
      <AssetLoad kind="scenarios" pending={query.isPending} error={query.error} retry={() => void query.refetch()} />
      {query.data ? <EditScenario scenario={query.data} /> : null}
    </main>
  );
}

function EditScenario({ scenario }: { scenario: ScenarioDetail }) {
  const [params, setParams] = useSearchParams();
  const tab = tabOf(params.get('tab'));
  const notice = useSavedNotice();
  const goTo = (next: ScenarioTab) => setParams({ tab: next }, { replace: true });

  return (
    <>
      <h1>{scenario.title}</h1>
      {notice.notice ? <Notice>{notice.notice}</Notice> : null}
      <div className="scenario-editor">
        <CheckPanel scenarioId={scenario.id} goTo={goTo} />
        <div className="scenario-editor__main">
          <TabList current={tab} onChange={goTo} />
          {SCENARIO_TABS.map((entry) => (
            <div
              key={entry}
              id={`scenario-panel-${entry}`}
              role="tabpanel"
              aria-labelledby={`scenario-tab-${entry}`}
              hidden={entry !== tab}
              className="scenario-editor__panel"
            >
              {panelOf(entry, scenario, goTo)}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function panelOf(tab: ScenarioTab, scenario: ScenarioDetail, goTo: (tab: ScenarioTab) => void): ReactNode {
  if (tab === 'basics') return <BasicsTab scenario={scenario} />;
  if (tab === 'materials') return <MaterialsTab scenario={scenario} />;
  if (tab === 'openings') return <OpeningsTab scenario={scenario} />;
  if (tab === 'characters') return <CharactersTab scenario={scenario} goTo={goTo} />;
  if (tab === 'items') return <ItemsTab scenario={scenario} goTo={goTo} />;
  if (tab === 'npcs') return <NpcsTab scenario={scenario} goTo={goTo} />;
  if (tab === 'map') return <MapTab scenario={scenario} goTo={goTo} />;
  if (tab === 'monsters') return <MonstersTab scenario={scenario} goTo={goTo} />;
  if (tab === 'quests') return <QuestsTab scenario={scenario} goTo={goTo} />;
  return <PublishTab scenario={scenario} />;
}

function TabList({ current, onChange }: { current: ScenarioTab; onChange: (tab: ScenarioTab) => void }) {
  return (
    <div className="scenario-tabs" role="tablist" aria-label="시나리오의 칸">
      {SCENARIO_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          id={`scenario-tab-${tab}`}
          aria-selected={tab === current}
          aria-controls={`scenario-panel-${tab}`}
          className="scenario-tab"
          onClick={() => onChange(tab)}
        >
          {sectionLabel(tab)}
        </button>
      ))}
    </div>
  );
}
