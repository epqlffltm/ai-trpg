// web/apps/web/src/pages/home/RankingRows.tsx
// 첫 화면의 이번 주 인기(#985). TRPG 의 시나리오, chat 의 캐릭터, story 의 세계관을 서비스마다 한 줄씩, 1위부터.
// 최근 7일에 시작한 수(테이블, 대화, 세션)로 늘어놓는다. 서버마다 따로 부르고 따로 실패한다(#593). 로그인하지 않아도 보인다.
// 카드마다 순위와 수("1위", "이번 주 12회")를 태그 앞에 붙인다.

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { CharacterCard } from '../chat/browse/CharacterCard';
import { ItemCard } from '../../components/ItemCard';
import { StoryWorldCard } from '../story/StoryWorldCard';
import { genreLabel } from '../trpg/labels';
import { ratingBadge } from './labels';
import { listStatus } from './listStatus';
import { characterRankingQuery, scenarioRankingQuery, worldRankingQuery } from './queries';
import { rankBadges } from './rankingView';

export function RankingRows({ signedIn }: { signedIn: boolean }) {
  return (
    <>
      <ScenarioRankingRow signedIn={signedIn} />
      <CharacterRankingRow signedIn={signedIn} />
      <WorldRankingRow signedIn={signedIn} />
    </>
  );
}

function ScenarioRankingRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(scenarioRankingQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="이번 주 인기 시나리오"
      status={listStatus(query, items.length)}
      emptyText="이번 주에 열린 테이블이 아직 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ol className="item-grid">
        {items.map(({ rank, starts, listing }) => (
          <ItemCard
            key={listing.scenario_id}
            to={`/trpg/scenarios/${listing.scenario_id}`}
            title={listing.title}
            description={listing.tagline}
            meta={[...rankBadges(rank, starts), ratingBadge(listing.rating), listing.genre ? genreLabel(listing.genre) : null]}
          />
        ))}
      </ol>
    </ListSection>
  );
}

function CharacterRankingRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(characterRankingQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="이번 주 인기 캐릭터"
      status={listStatus(query, items.length)}
      emptyText="이번 주에 시작한 대화가 아직 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ol className="item-grid">
        {items.map(({ rank, starts, character }) => (
          <CharacterCard key={character.id} character={character} badges={rankBadges(rank, starts)} />
        ))}
      </ol>
    </ListSection>
  );
}

function WorldRankingRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(worldRankingQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="이번 주 인기 세계관"
      status={listStatus(query, items.length)}
      emptyText="이번 주에 시작한 이야기가 아직 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ol className="item-grid">
        {items.map(({ rank, starts, world }) => (
          <StoryWorldCard key={world.id} world={world} badges={rankBadges(rank, starts)} />
        ))}
      </ol>
    </ListSection>
  );
}
