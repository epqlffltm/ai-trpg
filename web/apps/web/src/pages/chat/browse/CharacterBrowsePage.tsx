// web/apps/web/src/pages/chat/browse/CharacterBrowsePage.tsx
// 캐릭터 탐색(C1, /chat). 공개된 캐릭터를 최근에 게시한 것부터 카드 격자로 보이고, "더 보기"로 이어 읽는다(한 쪽 20개).
// 로그인하지 않아도 열린다(#530, 전체이용가만). 카드를 누르면 소개(C2)로 간다.
// 거르기(장르, 태그)는 asset 서버의 목록에 조건이 아직 없어 두지 않는다. 다음 쪽을 읽지 못해도 읽은 쪽은 남긴다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { useSession } from '../../../auth/useSession';
import { characterBrowseQuery } from '../chatQueries';
import { AdultCharacterHint } from './AdultCharacterHint';
import { CharacterCard } from './CharacterCard';

export function CharacterBrowsePage() {
  const signedIn = useSession() !== null;
  const query = useInfiniteQuery(characterBrowseQuery(signedIn));
  const pages = query.data?.pages ?? [];
  const items = pages.flatMap((page) => page.items);

  return (
    <main className="page">
      <div className="page-head">
        <h1>캐릭터 찾기</h1>
        {signedIn ? <Link to="/chat/studio/characters">캐릭터 만들기</Link> : null}
      </div>
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
