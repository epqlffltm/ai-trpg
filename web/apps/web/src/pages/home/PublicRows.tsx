// web/apps/web/src/pages/home/PublicRows.tsx
// 공개된 것. TRPG 의 시나리오, chat 의 캐릭터, story 의 세계관을 서비스마다 한 줄씩. 로그인하지 않아도 보인다(#530).

import { ListSection } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { ItemCard } from '../../components/ItemCard';
import { genreLabel } from '../trpg/labels';
import { ratingBadge } from './labels';
import { listStatus } from './listStatus';
import { StoryWorldCard } from '../story/StoryWorldCard';
import { publicCharactersQuery, publicScenariosQuery, publicWorldsQuery } from './queries';

export function PublicRows({ signedIn }: { signedIn: boolean }) {
  return (
    <>
      <PublicScenariosRow signedIn={signedIn} />
      <PublicCharactersRow signedIn={signedIn} />
      <PublicWorldsRow signedIn={signedIn} />
    </>
  );
}

function PublicScenariosRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(publicScenariosQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="새로 공개된 시나리오"
      status={listStatus(query, items.length)}
      action={<Link to="/trpg">더 보기</Link>}
      emptyText="아직 공개된 시나리오가 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((listing) => (
          <ItemCard
            key={listing.scenario_id}
            to={`/trpg/scenarios/${listing.scenario_id}`}
            title={listing.title}
            description={listing.tagline}
            meta={[ratingBadge(listing.rating), ...listing.genres.map(genreLabel)]}
          />
        ))}
      </ul>
    </ListSection>
  );
}

function PublicCharactersRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(publicCharactersQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="새로 공개된 캐릭터"
      status={listStatus(query, items.length)}
      action={<Link to="/chat">더 보기</Link>}
      emptyText="아직 공개된 캐릭터가 없습니다."
      onRetry={() => void query.refetch()}
    >
      <ul className="item-grid">
        {items.map((character) => (
          <ItemCard
            key={character.id}
            to={`/chat/characters/${character.id}`}
            title={character.name}
            meta={[ratingBadge(character.rating), ...character.tags]}
          />
        ))}
      </ul>
    </ListSection>
  );
}

function PublicWorldsRow({ signedIn }: { signedIn: boolean }) {
  const query = useQuery(publicWorldsQuery(signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title="새로 공개된 세계관"
      status={listStatus(query, items.length)}
      action={<Link to="/story">더 보기</Link>}
      emptyText="아직 공개된 세계관이 없습니다."
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
