// web/apps/web/src/pages/chat/browse/CharacterBrowsePage.tsx
// 캐릭터 탐색(C1, /chat). 공개된 캐릭터를 최근에 게시한 것부터(또는 인기순, ?sort=popular, #985) 카드 격자로 보이고, "더 보기"로 이어 읽는다(한 쪽 20개).
// 로그인하지 않아도 열린다(#530, 전체이용가만). 카드를 누르면 소개(C2)로 간다.
// 거르기(장르, 태그)는 asset 서버의 목록에 조건이 아직 없어 두지 않는다. 다음 쪽을 읽지 못해도 읽은 쪽은 남긴다.
// 모양은 Stitch 16번(12번과 같은 틀): 위에 chat 배너(#994), 최신순이면 이번 주 인기 줄(#985), 그 아래 "전체 캐릭터"의 격자.
// 머리 줄 오른쪽에 "내 대화"(최근 대화 화면 /conversations)와 "캐릭터 만들기". 둘 다 로그인했을 때만 둔다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router';
import { parseOrder, type ListingOrder } from '../../../api/listingOrder';
import { useSession } from '../../../auth/useSession';
import { OrderChips } from '../../../components/OrderChips';
import { PromoBanner } from '../../home/PromoBanner';
import { CharacterRankingRow } from '../../home/RankingRows';
import { characterBrowseQuery } from '../chatQueries';
import { AdultCharacterHint } from './AdultCharacterHint';
import { CharacterCard } from './CharacterCard';

export function CharacterBrowsePage() {
  const signedIn = useSession() !== null;
  const [params, setParams] = useSearchParams();
  const order = parseOrder(params.get('sort'));
  const query = useInfiniteQuery(characterBrowseQuery(signedIn, order));
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);

  return (
    <main className="page">
      <div className="page-head">
        <h1>캐릭터 찾기</h1>
        {signedIn ? (
          <nav className="page-head__links" aria-label="내 chat">
            <Link to="/conversations">내 대화</Link>
            <Link to="/chat/studio/characters">캐릭터 만들기</Link>
          </nav>
        ) : null}
      </div>
      <PromoBanner signedIn={signedIn} service="chat" />
      {order === 'popular' ? null : <CharacterRankingRow signedIn={signedIn} />}
      <h2 className="explore-all">전체 캐릭터</h2>
      <OrderChips order={order} onChange={(next: ListingOrder) => setParams(next === 'popular' ? { sort: next } : {})} />
      <AdultCharacterHint signedIn={signedIn} />
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError && items.length === 0 ? <LoadFailed onRetry={() => void query.refetch()} /> : null}
      {query.isSuccess && items.length === 0 ? <p className="empty-state">아직 공개된 캐릭터가 없습니다.</p> : null}
      {items.length > 0 ? (
        <>
          <p className="result-count">{pages[0]?.total ?? items.length}명</p>
          <ul className="item-grid" aria-label="캐릭터">
            {items.map((character) => (
              <CharacterCard key={character.id} character={character} />
            ))}
          </ul>
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
