// web/apps/web/src/pages/search/SearchPage.tsx
// 작품 검색 결과(#984, /search?q=). 로그인하지 않아도 열린다. 머리의 검색칸(layout/HeaderSearch.tsx)이 이리로 보낸다.
// TRPG 의 시나리오, chat 의 캐릭터, story 의 세계관을 서비스마다 묶는다. 서버마다 따로 부르고 섞어 정렬하지 않는다(#593).
// 묶음마다 최근에 공개한 것부터 앞의 SEARCH_LIMIT 개와 찾은 수다. 검색어가 규칙에 맞지 않으면 부르지 않고 까닭을 적는다.
// 태그가 아닌 검색어(20자까지)면 맨 앞에 제작자(인증 서버, 닉네임으로 찾음)를 묶는다. 내가 막은 제작자는 뺀다(#988).
// 모양은 Stitch 36번: 큰 명조 제목, 묶음 제목은 명조.

import { ListSection, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';
import { CREATOR_SEARCH_MAX_LENGTH } from '../../api/creators';
import { meQuery } from '../../auth/queries';
import { useSession } from '../../auth/useSession';
import { ItemCard } from '../../components/ItemCard';
import { usageTags } from '../../format/usage';
import { CharacterCard } from '../chat/browse/CharacterCard';
import { ratingBadge } from '../home/labels';
import { listStatus } from '../home/listStatus';
import { StoryWorldCard } from '../story/StoryWorldCard';
import { genreLabel } from '../trpg/labels';
import { characterSearchQuery, creatorSearchQuery, scenarioSearchQuery, worldSearchQuery } from './searchQueries';
import { isSearchable, normalizeSearch, searchesCreators, searchProblem } from './searchView';

export function SearchPage() {
  const [params] = useSearchParams();
  const q = normalizeSearch(params.get('q') ?? '');
  const problem = searchProblem(q);
  const signedIn = useSession() !== null;

  return (
    <main className="page works-page">
      <h1>{q === '' ? '작품 검색' : `"${q}" 검색 결과`}</h1>
      <p className="hint">이름이나 한 줄 소개, 만든 사람의 닉네임으로 찾습니다. #으로 시작하면 그 태그가 붙은 작품을 찾습니다.</p>
      {problem ? <Notice tone="error">{problem}</Notice> : null}
      {q === '' ? <p className="empty-state">위쪽의 검색칸에 찾을 말을 적어 주세요.</p> : null}
      {isSearchable(q) ? (
        <>
          {searchesCreators(q, CREATOR_SEARCH_MAX_LENGTH) ? <CreatorResults q={q} signedIn={signedIn} /> : null}
          <ScenarioResults q={q} signedIn={signedIn} />
          <CharacterResults q={q} signedIn={signedIn} />
          <WorldResults q={q} signedIn={signedIn} />
        </>
      ) : null}
    </main>
  );
}

type ResultsProps = { q: string; signedIn: boolean };

function CreatorResults({ q, signedIn }: ResultsProps) {
  const query = useQuery(creatorSearchQuery(q));
  const me = useQuery({ ...meQuery(), enabled: signedIn });
  const blocked = new Set(me.data?.blocks.creators ?? []);
  const items = (query.data?.items ?? []).filter((creator) => !blocked.has(creator.public_id));
  return (
    <ListSection
      title={query.data ? `제작자 ${items.length}명` : '제작자'}
      status={listStatus(query, items.length)}
      emptyText="찾은 제작자가 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((creator) => (
          <ItemCard key={creator.public_id} to={`/creators/${encodeURIComponent(creator.public_id)}`} title={creator.nickname} description={creator.bio} meta={['제작자']} />
        ))}
      </ul>
    </ListSection>
  );
}

function ScenarioResults({ q, signedIn }: ResultsProps) {
  const query = useQuery(scenarioSearchQuery(q, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('TRPG 시나리오', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="찾은 시나리오가 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((listing) => (
          <ItemCard
            key={listing.scenario_id}
            to={`/trpg/scenarios/${listing.scenario_id}`}
            title={listing.title}
            description={listing.tagline}
            meta={[ratingBadge(listing.rating), listing.genre ? genreLabel(listing.genre) : null, ...usageTags('테이블', listing.start_count, listing.heart_count)]}
          />
        ))}
      </ul>
    </ListSection>
  );
}

function CharacterResults({ q, signedIn }: ResultsProps) {
  const query = useQuery(characterSearchQuery(q, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('chat 캐릭터', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="찾은 캐릭터가 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((character) => (
          <CharacterCard key={character.id} character={character} />
        ))}
      </ul>
    </ListSection>
  );
}

function WorldResults({ q, signedIn }: ResultsProps) {
  const query = useQuery(worldSearchQuery(q, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('story 세계관', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="찾은 세계관이 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((world) => (
          <StoryWorldCard key={world.id} world={world} />
        ))}
      </ul>
    </ListSection>
  );
}

/** 묶음의 제목. 찾은 수를 알면 붙인다 */
function sectionTitle(name: string, total: number | undefined): string {
  return total === undefined ? name : `${name} ${total}개`;
}
