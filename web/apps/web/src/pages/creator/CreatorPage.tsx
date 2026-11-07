// web/apps/web/src/pages/creator/CreatorPage.tsx
// 제작자 페이지(#992, /creators/:publicId). 로그인하지 않아도 열린다. 작품의 소개에서 "만든 사람"을 누르면 온다.
// 표시 이름(닉네임)과 소개는 인증 서버, 공개 작품은 서비스마다 그 서버가 준다. 서버마다 따로 부르고 섞어 정렬하지 않는다(#593).
// 프로필을 읽지 못해도 작품의 묶음은 따로 보인다. 없거나 탈퇴한 제작자(404)면 그 안내만 보인다.
// 이름 아래에 팔로워 수와 팔로우 단추(#989, FollowButton), 로그인했으면 "차단하기"(#988, CreatorBlockButton)를 둔다.
// 모양은 Stitch 37번: 머리는 종이 한 장(이름, 소개, 단추), 묶음 제목은 명조.

import { Button, ListSection, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { ApiError } from '../../api/errors';
import { useSession } from '../../auth/useSession';
import { CreatorBlockButton } from '../../components/CreatorBlockButton';
import { FollowButton } from '../../components/FollowButton';
import { ItemCard } from '../../components/ItemCard';
import { usageTags } from '../../format/usage';
import { CharacterCard } from '../chat/browse/CharacterCard';
import { ratingBadge } from '../home/labels';
import { listStatus } from '../home/listStatus';
import { StoryWorldCard } from '../story/StoryWorldCard';
import { genreLabel } from '../trpg/labels';
import { creatorCharactersQuery, creatorQuery, creatorScenariosQuery, creatorWorldsQuery } from './creatorQueries';

export function CreatorPage() {
  const { publicId = '' } = useParams();
  const signedIn = useSession() !== null;
  const creator = useQuery(creatorQuery(publicId));

  if (creator.error instanceof ApiError && creator.error.status === 404) {
    return (
      <main className="page page--medium">
        <h1>제작자</h1>
        <Notice>없거나 탈퇴한 제작자입니다.</Notice>
      </main>
    );
  }
  return (
    <main className="page works-page">
      <header className="creator-head">
        <h1>{creator.data?.nickname ?? '제작자'}</h1>
        {creator.data?.bio ? <p className="prose creator-head__bio">{creator.data.bio}</p> : null}
        {creator.data ? (
          <p className="creator-head__actions">
            <FollowButton creatorId={publicId} leading={false} />
            <CreatorBlockButton creatorId={publicId} />
          </p>
        ) : null}
      </header>
      {creator.isError ? (
        <Notice tone="error">
          제작자의 소개를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void creator.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      <CreatorScenarios publicId={publicId} signedIn={signedIn} />
      <CreatorCharacters publicId={publicId} signedIn={signedIn} />
      <CreatorWorlds publicId={publicId} signedIn={signedIn} />
    </main>
  );
}

type WorksProps = { publicId: string; signedIn: boolean };

function CreatorScenarios({ publicId, signedIn }: WorksProps) {
  const query = useQuery(creatorScenariosQuery(publicId, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('TRPG 시나리오', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="공개한 시나리오가 없습니다."
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

function CreatorCharacters({ publicId, signedIn }: WorksProps) {
  const query = useQuery(creatorCharactersQuery(publicId, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('chat 캐릭터', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="공개한 캐릭터가 없습니다."
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

function CreatorWorlds({ publicId, signedIn }: WorksProps) {
  const query = useQuery(creatorWorldsQuery(publicId, signedIn));
  const items = query.data?.items ?? [];
  return (
    <ListSection
      title={sectionTitle('story 세계관', query.data?.total)}
      status={listStatus(query, items.length)}
      emptyText="공개한 세계관이 없습니다."
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

/** 묶음의 제목. 공개한 수를 알면 붙인다 */
function sectionTitle(name: string, total: number | undefined): string {
  return total === undefined ? name : `${name} ${total}개`;
}
