// web/apps/web/src/pages/me/hearts/MyHeartsPage.tsx
// 내 관심 작품(#989, /me/hearts). 로그인해야 열린다. 마이페이지의 "관심 작품"에서 온다.
// TRPG 시나리오, chat 캐릭터, story 세계관을 서버마다 따로 부르고 서비스마다 묶는다(#593). 최근에 둔 것부터다.
// 지금 볼 수 있는 것만 나온다(공개를 내렸거나 볼 수 없게 된 것은 빠진다). 관심을 거두는 것은 작품의 소개에서 한다.

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { fetchHeartedCharacters, fetchHeartedScenarios, fetchHeartedWorlds } from '../../../api/hearts';
import { ItemCard } from '../../../components/ItemCard';
import { usageTags } from '../../../format/usage';
import { CharacterCard } from '../../chat/browse/CharacterCard';
import { ratingBadge } from '../../home/labels';
import { listStatus } from '../../home/listStatus';
import { StoryWorldCard } from '../../story/StoryWorldCard';
import { genreLabel } from '../../trpg/labels';

export function MyHeartsPage() {
  return (
    <main className="page">
      <h1>관심 작품</h1>
      <p className="hint">작품의 소개에서 ♡ 관심을 누르면 여기에 모입니다. 다시 누르면 빠집니다.</p>
      <HeartedScenarios />
      <HeartedCharacters />
      <HeartedWorlds />
    </main>
  );
}

function HeartedScenarios() {
  const query = useQuery({ queryKey: ['hearts', 'mine', 'scenario'], queryFn: ({ signal }) => fetchHeartedScenarios(signal) });
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('TRPG 시나리오', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="관심을 둔 시나리오가 없습니다."
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

function HeartedCharacters() {
  const query = useQuery({ queryKey: ['hearts', 'mine', 'character'], queryFn: ({ signal }) => fetchHeartedCharacters(signal) });
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('chat 캐릭터', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="관심을 둔 캐릭터가 없습니다."
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

function HeartedWorlds() {
  const query = useQuery({ queryKey: ['hearts', 'mine', 'world'], queryFn: ({ signal }) => fetchHeartedWorlds(signal) });
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('story 세계관', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="관심을 둔 세계관이 없습니다."
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

/** 묶음의 제목. 수를 알면 붙인다 */
function sectionTitle(name: string, total: number | undefined): string {
  return total === undefined ? name : `${name} ${total}개`;
}
