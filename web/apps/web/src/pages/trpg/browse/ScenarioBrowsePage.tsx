// web/apps/web/src/pages/trpg/browse/ScenarioBrowsePage.tsx
// 시나리오 탐색(B1, /trpg). 공개된 시나리오를 최근 공개한 것부터 보이고, 장르·인원·태그로 거른다.
// 로그인하지 않아도 열린다(#530, 전체이용가만). 카드를 누르면 소개(B2)로 간다.
//
// 거르는 조건은 주소의 쿼리에 둔다(filters.ts). 쪽은 "더 보기"로 이어 읽는다(한 쪽 20개).
// 다음 쪽을 읽지 못해도 이미 읽은 쪽은 남기고 그 자리에서 다시 시도한다. 만든 사람의 이름은 쪽마다 한 번에 묻는다(#532).

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router';
import type { ListingFilters } from '../../../api/listings';
import type { PublicListing } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { ItemCard } from '../../../components/ItemCard';
import { usePublicNames, type NameLookup } from '../../../hooks/usePublicNames';
import { ratingBadge } from '../../home/labels';
import { AdultContentHint } from '../AdultContentHint';
import { genreLabel, playersLabel } from '../labels';
import { listingsQuery } from '../queries';
import { BrowseFilters } from './BrowseFilters';
import { hasFilters, parseFilters, toSearchParams } from './filters';

export function ScenarioBrowsePage() {
  const [params, setParams] = useSearchParams();
  const filters = parseFilters(params);
  const signedIn = useSession() !== null;
  const query = useInfiniteQuery(listingsQuery(filters, signedIn));
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);
  const nameOf = usePublicNames(pages.map((page) => page.items.map((item) => item.creator_id)));

  function change(next: ListingFilters) {
    setParams(toSearchParams(next));
  }

  return (
    <main className="page">
      <h1>시나리오 찾기</h1>
      <BrowseFilters filters={filters} onChange={change} />
      <AdultContentHint />
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? <LoadFailed onRetry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? <Empty filtered={hasFilters(filters)} onClear={() => change({})} /> : null}
      {items.length > 0 ? (
        <>
          <p className="result-count">{pages[0]?.total ?? items.length}개</p>
          <ScenarioGrid items={items} nameOf={nameOf} />
        </>
      ) : null}
      {query.isFetchNextPageError ? <LoadFailed onRetry={() => void query.fetchNextPage()} /> : null}
      {query.hasNextPage && !query.isFetchNextPageError ? (
        <div className="load-more">
          <Button variant="secondary" busy={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </main>
  );
}

function ScenarioGrid({ items, nameOf }: { items: PublicListing[]; nameOf: NameLookup }) {
  return (
    <ul className="item-grid">
      {items.map((listing) => (
        <ItemCard
          key={listing.scenario_id}
          to={`/trpg/scenarios/${listing.scenario_id}`}
          title={listing.title}
          description={listing.tagline}
          byline={nameOf(listing.creator_id)}
          meta={[ratingBadge(listing.rating), ...listing.genres.map(genreLabel), playersLabel(listing.recommended_players)]}
        />
      ))}
    </ul>
  );
}

function Empty({ filtered, onClear }: { filtered: boolean; onClear: () => void }) {
  if (!filtered) return <p className="empty-state">아직 공개된 시나리오가 없습니다.</p>;
  return (
    <div className="empty-state">
      <p>조건에 맞는 시나리오가 없습니다.</p>
      <Button variant="secondary" onClick={onClear}>
        조건 모두 풀기
      </Button>
    </div>
  );
}

function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <Notice tone="error">
      목록을 불러오지 못했습니다.{' '}
      <Button variant="quiet" onClick={onRetry}>
        다시 시도
      </Button>
    </Notice>
  );
}
