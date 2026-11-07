// web/apps/web/src/pages/trpg/browse/ScenarioBrowsePage.tsx
// 시나리오 탐색(B1, /trpg). 공개된 시나리오를 최근 공개한 것부터(또는 인기순, #985) 보이고, 장르·인원·태그로 거른다.
// 카드에 연 테이블의 수와 관심의 수(#989)를 붙인다.
// 로그인하지 않아도 열린다(#530, 전체이용가만). 카드를 누르면 소개(B2)로 간다.
//
// 거르는 조건은 주소의 쿼리에 둔다(filters.ts). 쪽은 "더 보기"로 이어 읽는다(한 쪽 20개).
// 다음 쪽을 읽지 못해도 이미 읽은 쪽은 남기고 그 자리에서 다시 시도한다. 만든 사람의 이름은 쪽마다 한 번에 묻는다(#532).
// 모양은 Stitch 12번: 위에 TRPG 배너(#994), 거르지 않았으면 이번 주 인기 줄(#985), 그 아래 "전체 시나리오"의 거르기와 격자.
// 위쪽 오른편에 테이블 로비와 지나간 테이블. 공식·장르마다의 줄은 서버에 그 목록이 없어 두지 않는다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import type { ListingFilters } from '../../../api/listings';
import type { PublicListing } from '../../../api/types';
import { useSession } from '../../../auth/useSession';
import { ItemCard } from '../../../components/ItemCard';
import { usageTags } from '../../../format/usage';
import { usePublicNames, type NameLookup } from '../../../hooks/usePublicNames';
import { ratingBadge } from '../../home/labels';
import { PromoBanner } from '../../home/PromoBanner';
import { ScenarioRankingRow } from '../../home/RankingRows';
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
      <div className="page-head">
        <h1>시나리오 찾기</h1>
        <nav className="page-head__links" aria-label="테이블">
          <Link to="/trpg/lobby">테이블 로비</Link>
          <Link to="/trpg/tables/past">지나간 테이블</Link>
        </nav>
      </div>
      <PromoBanner signedIn={signedIn} service="TRPG" />
      {hasFilters(filters) || filters.sort === 'popular' ? null : <ScenarioRankingRow signedIn={signedIn} />}
      <h2 className="explore-all">전체 시나리오</h2>
      <BrowseFilters filters={filters} onChange={change} />
      <AdultContentHint />
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? <LoadFailed onRetry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? <Empty filtered={hasFilters(filters)} onClear={() => change({ sort: filters.sort })} /> : null}
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
          meta={[
            ratingBadge(listing.rating),
            listing.genre ? genreLabel(listing.genre) : null,
            playersLabel(listing.recommended_players),
            ...usageTags('테이블', listing.start_count, listing.heart_count),
          ]}
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
