// web/apps/web/src/pages/story/studio/StoryWorldEditPage.tsx
// 세계관 고치기(D7, /story/studio/worlds/:worldId?tab=). 칸의 묶음마다 탭이 있고 탭마다 저장한다. PC 가 기본이다.
// 탭은 모두 그려 두고 고르지 않은 것을 숨긴다. 다른 탭에 갔다 와도 저장하지 않은 입력이 남는다.
// 옆(좁은 화면에서는 위)에 게시 점검을 늘 둔다. 막는 것을 누르면 그 탭으로 간다. 모양은 캐릭터 고치기(C6)와 같다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import type { StoryWorldDetail } from '../../../api/storyWorlds';
import { WorldBasicsTab } from './WorldBasicsTab';
import { WorldCastTab } from './WorldCastTab';
import { WorldCheckPanel } from './WorldCheckPanel';
import { WorldEndingsTab } from './WorldEndingsTab';
import { WorldEventsTab } from './WorldEventsTab';
import { WorldIntroTab } from './WorldIntroTab';
import { WorldItemsTab } from './WorldItemsTab';
import { WorldLorebooksTab } from './WorldLorebooksTab';
import { WorldMapTab } from './WorldMapTab';
import { WorldProgressTab } from './WorldProgressTab';
import { WorldPublishTab } from './WorldPublishTab';
import { WORLDS_PATH } from './worldPaths';
import { isMissingWorld } from './worldProblem';
import { worldQuery } from './worldQueries';
import { WORLD_TABS, worldTabLabel, worldTabOf, type WorldTab } from './worldTabs';

export function StoryWorldEditPage() {
  const { worldId = '' } = useParams();
  const query = useQuery(worldQuery(worldId));
  return (
    <main className="page">
      <p>
        <Link to={WORLDS_PATH}>내 세계관</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && isMissingWorld(query.error) ? <Notice tone="error">세계관을 찾을 수 없습니다. 지워졌을 수 있습니다.</Notice> : null}
      {query.isError && !isMissingWorld(query.error) ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.data ? <EditWorld world={query.data} /> : null}
    </main>
  );
}

function wasCreated(state: unknown): boolean {
  return state !== null && typeof state === 'object' && (state as Record<string, unknown>).created === true;
}

function EditWorld({ world }: { world: StoryWorldDetail }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const tab = worldTabOf(params.get('tab'));
  const goTo = (next: WorldTab) => setParams({ tab: next }, { replace: true });

  return (
    <>
      <h1>{world.name}</h1>
      {wasCreated(location.state) ? <Notice>만들었습니다.</Notice> : null}
      <div className="scenario-editor">
        <WorldCheckPanel worldId={world.id} goTo={goTo} />
        <div className="scenario-editor__main">
          <TabList current={tab} onChange={goTo} />
          {WORLD_TABS.map((entry) => (
            <div key={entry} id={`world-panel-${entry}`} role="tabpanel" aria-labelledby={`world-tab-${entry}`} hidden={entry !== tab}>
              {panelOf(entry, world)}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function panelOf(tab: WorldTab, world: StoryWorldDetail): ReactNode {
  if (tab === 'basics') return <WorldBasicsTab world={world} />;
  if (tab === 'intro') return <WorldIntroTab world={world} />;
  if (tab === 'progress') return <WorldProgressTab world={world} />;
  if (tab === 'map') return <WorldMapTab world={world} />;
  if (tab === 'items') return <WorldItemsTab world={world} />;
  if (tab === 'cast') return <WorldCastTab world={world} />;
  if (tab === 'events') return <WorldEventsTab world={world} />;
  if (tab === 'endings') return <WorldEndingsTab world={world} />;
  if (tab === 'lorebooks') return <WorldLorebooksTab world={world} />;
  return <WorldPublishTab world={world} />;
}

function TabList({ current, onChange }: { current: WorldTab; onChange: (tab: WorldTab) => void }) {
  return (
    <div className="scenario-tabs" role="tablist" aria-label="세계관의 칸">
      {WORLD_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          id={`world-tab-${tab}`}
          aria-selected={tab === current}
          aria-controls={`world-panel-${tab}`}
          className="scenario-tab"
          onClick={() => onChange(tab)}
        >
          {worldTabLabel(tab)}
        </button>
      ))}
    </div>
  );
}
