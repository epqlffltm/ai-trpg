// web/apps/web/src/pages/chat/studio/characters/CharacterEditPage.tsx
// 캐릭터 고치기(C6, /chat/studio/characters/:characterId?tab=). 칸의 묶음마다 탭이 있고 탭마다 저장한다.
// 탭은 모두 그려 두고 고르지 않은 것을 숨긴다. 다른 탭에 갔다 와도 저장하지 않은 입력이 남는다.
// 옆(좁은 화면에서는 위)에 게시 점검을 늘 둔다. 문제를 누르면 그 탭으로 간다. 모양은 시나리오 고치기(B9)와 같다.
// 운영자가 숨긴 캐릭터면 위에 알린다(남에게 보이지 않고 주인만 쓴다).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import type { AssetCharacterDetail } from '../../../../api/types';
import { BasicsTab } from './BasicsTab';
import { CHARACTERS_PATH } from './characterPaths';
import { isMissingCharacter } from './characterProblem';
import { characterQuery } from './characterQueries';
import { CHARACTER_TABS, sectionLabel, tabOf, type CharacterTab } from './characterTabs';
import { CheckPanel } from './CheckPanel';
import { IntroTab } from './IntroTab';
import { ItemsTab } from './ItemsTab';
import { MapTab } from './MapTab';
import { PublishTab } from './PublishTab';
import { SpeechTab } from './SpeechTab';
import { StartsTab } from './StartsTab';

export function CharacterEditPage() {
  const { characterId = '' } = useParams();
  const query = useQuery(characterQuery(characterId));
  return (
    <main className="page">
      <p>
        <Link to={CHARACTERS_PATH}>내 캐릭터</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && isMissingCharacter(query.error) ? <Notice tone="error">캐릭터를 찾을 수 없습니다. 지워졌을 수 있습니다.</Notice> : null}
      {query.isError && !isMissingCharacter(query.error) ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.data ? <EditCharacter character={query.data} /> : null}
    </main>
  );
}

function wasCreated(state: unknown): boolean {
  return state !== null && typeof state === 'object' && (state as Record<string, unknown>).created === true;
}

function EditCharacter({ character }: { character: AssetCharacterDetail }) {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const tab = tabOf(params.get('tab'));
  const goTo = (next: CharacterTab) => setParams({ tab: next }, { replace: true });

  return (
    <>
      <h1>{character.name}</h1>
      {wasCreated(location.state) ? <Notice>만들었습니다.</Notice> : null}
      {character.hidden_at ? (
        <Notice tone="error">운영자가 숨긴 캐릭터입니다. 공개 목록과 남의 새 대화에서 빠지고, 나만 씁니다.</Notice>
      ) : null}
      <div className="scenario-editor">
        <CheckPanel characterId={character.id} goTo={goTo} />
        <div className="scenario-editor__main">
          <TabList current={tab} onChange={goTo} />
          {CHARACTER_TABS.map((entry) => (
            <div
              key={entry}
              id={`character-panel-${entry}`}
              role="tabpanel"
              aria-labelledby={`character-tab-${entry}`}
              hidden={entry !== tab}
            >
              {panelOf(entry, character)}
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function panelOf(tab: CharacterTab, character: AssetCharacterDetail): ReactNode {
  if (tab === 'basics') return <BasicsTab character={character} />;
  if (tab === 'intro') return <IntroTab character={character} />;
  if (tab === 'speech') return <SpeechTab character={character} />;
  if (tab === 'starts') return <StartsTab character={character} />;
  if (tab === 'map') return <MapTab character={character} />;
  if (tab === 'items') return <ItemsTab character={character} />;
  return <PublishTab character={character} />;
}

function TabList({ current, onChange }: { current: CharacterTab; onChange: (tab: CharacterTab) => void }) {
  return (
    <div className="scenario-tabs" role="tablist" aria-label="캐릭터의 칸">
      {CHARACTER_TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          role="tab"
          id={`character-tab-${tab}`}
          aria-selected={tab === current}
          aria-controls={`character-panel-${tab}`}
          className="scenario-tab"
          onClick={() => onChange(tab)}
        >
          {sectionLabel(tab)}
        </button>
      ))}
    </div>
  );
}
