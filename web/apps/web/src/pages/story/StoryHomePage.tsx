// web/apps/web/src/pages/story/StoryHomePage.tsx
// story 의 첫 화면(/story). 로그인하지 않아도 열린다. 위에 공개 세계관(20 개씩 "더 보기", 누르면 소개 D1).
// 공개 세계관은 최신순과 인기순(?sort=popular, #985)으로 줄 세운다.
// 로그인했으면 내 세션(최근 것부터, 20 개씩 "더 보기")과 게시한 내 세계관으로 새로 시작. 운영자에게는 "세계관 만들기"(D7)와 "JSON 으로 세계관 넣기"로 가는 길이 있다.
// 시작하면 세계관의 마지막 판을 고정한 새 세션이 생기고 장면(D2)으로 간다. 모델은 지난번 세션의 것이다.
// 모양은 Stitch 17번(12번과 같은 틀): 맨 위에 내 세션(로그인했을 때), story 배너(#994), 최신순이면 이번 주 인기 줄(#985), "전체 세계관"의 격자.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Link, useLocation, useSearchParams } from 'react-router';
import { parseOrder, type ListingOrder } from '../../api/listingOrder';
import type { StorySessionSummary } from '../../api/story';
import type { StoryWorldSummary } from '../../api/storyWorlds';
import { isOperator } from '../../auth/roles';
import { useSession } from '../../auth/useSession';
import { OrderChips } from '../../components/OrderChips';
import { formatDateTime } from '../../format/dateTime';
import { PromoBanner } from '../home/PromoBanner';
import { WorldRankingRow } from '../home/RankingRows';
import { myStoryWorldsQuery, publicWorldsQuery, storySessionsQuery } from './storyQueries';
import { describeStartProblem } from './storyTurnProblem';
import { StoryWorldCard } from './StoryWorldCard';
import { progressLine } from './storyCastView';
import { useStartStorySession } from './useStartStorySession';

export function StoryHomePage() {
  const signedIn = useSession() !== null;
  return (
    <main className="page">
      <h1>story</h1>
      <p className="hint">세계관 하나를 걸으며 여러 인물을 만나는 이야기입니다. 세션마다 그때의 판으로 돕니다.</p>
      {signedIn ? <MySessions /> : <SignInNotice />}
      <PromoBanner signedIn={signedIn} service="story" />
      <PopularWorlds signedIn={signedIn} />
      <PublicWorlds signedIn={signedIn} />
      {signedIn ? <StartFromMyWorlds /> : null}
    </main>
  );
}

function PublicWorlds({ signedIn }: { signedIn: boolean }) {
  const [params, setParams] = useSearchParams();
  const order = parseOrder(params.get('sort'));
  const worlds = useInfiniteQuery(publicWorldsQuery(signedIn, order));
  const items = worlds.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="story-public">
      <h2 id="story-public">전체 세계관</h2>
      <OrderChips order={order} onChange={(next: ListingOrder) => setParams(next === 'popular' ? { sort: next } : {})} />
      {worlds.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {worlds.isError ? (
        <Notice tone="error">
          세계관을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void worlds.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {worlds.isSuccess && items.length === 0 ? <p className="empty-state">아직 공개된 세계관이 없습니다.</p> : null}
      <ul className="item-grid" aria-label="공개 세계관">
        {items.map((world) => (
          <StoryWorldCard key={world.id} world={world} />
        ))}
      </ul>
      {worlds.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={worlds.isFetchingNextPage} onClick={() => void worlds.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </section>
  );
}

/** 이번 주 인기 줄. 인기순으로 보는 중이면 아래 격자와 같아 두지 않는다 */
function PopularWorlds({ signedIn }: { signedIn: boolean }) {
  const [params] = useSearchParams();
  if (parseOrder(params.get('sort')) === 'popular') return null;
  return <WorldRankingRow signedIn={signedIn} />;
}

function SignInNotice() {
  const location = useLocation();
  return (
    <Notice>
      <Link to="/login" state={{ from: location.pathname }}>
        로그인
      </Link>
      하면 내 세션을 이어 가고 새로 시작합니다.
    </Notice>
  );
}

function MySessions() {
  const sessions = useInfiniteQuery(storySessionsQuery());
  const items = sessions.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="story-sessions">
      <h2 id="story-sessions">내 세션</h2>
      {sessions.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {sessions.isError ? (
        <Notice tone="error">
          세션을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void sessions.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {sessions.isSuccess && items.length === 0 ? <p className="empty-state">아직 시작한 이야기가 없습니다.</p> : null}
      <ul className="plain-list story-sessions" aria-label="내 세션">
        {items.map((session) => (
          <SessionRow key={session.id} session={session} />
        ))}
      </ul>
      {sessions.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={sessions.isFetchingNextPage} onClick={() => void sessions.fetchNextPage()}>
            더 보기
          </Button>
        </div>
      ) : null}
    </section>
  );
}

function SessionRow({ session }: { session: StorySessionSummary }) {
  return (
    <li className="story-sessions__row">
      <Link to={`/story/sessions/${encodeURIComponent(session.id)}`}>{session.title || session.world.name}</Link>
      <p className="hint">
        {[session.world.name, `${session.world.version}판`, progressLine(session.progress), session.model?.display_name ?? '모델 없음'].filter(Boolean).join(' · ')} · <time dateTime={session.updated_at}>{formatDateTime(session.updated_at)}</time>
      </p>
    </li>
  );
}

function StartFromMyWorlds() {
  const worlds = useQuery(myStoryWorldsQuery());
  const starting = useStartStorySession();
  const startable = (worlds.data?.items ?? []).filter((world) => world.latest_version !== null);
  const operator = isOperator(useSession());
  return (
    <section className="page-section" aria-labelledby="story-start">
      <h2 id="story-start">내 세계관으로 시작</h2>
      <p className="hint">
        내가 만들어 게시한 세계관으로 시작합니다.
        {operator ? (
          <>
            {' '}
            <Link to="/story/studio/worlds">세계관 만들기</Link> · <Link to="/story/worlds/import">JSON 으로 세계관 넣기</Link>
          </>
        ) : null}
      </p>
      {worlds.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {worlds.isError ? <Notice tone="error">세계관을 불러오지 못했습니다. 잠시 뒤에 다시 열어 주세요.</Notice> : null}
      {worlds.isSuccess && startable.length === 0 ? <p className="empty-state">게시한 세계관이 없습니다.</p> : null}
      {starting.error ? <Notice tone="error">{describeStartProblem(starting.error)}</Notice> : null}
      <ul className="plain-list story-worlds" aria-label="시작할 세계관">
        {startable.map((world) => (
          <WorldRow key={world.id} world={world} busy={starting.isPending && starting.variables?.worldId === world.id} disabled={starting.isPending} onStart={() => starting.mutate({ worldId: world.id })} />
        ))}
      </ul>
    </section>
  );
}

function WorldRow({ world, busy, disabled, onStart }: { world: StoryWorldSummary; busy: boolean; disabled: boolean; onStart: () => void }) {
  return (
    <li className="story-worlds__row">
      <span>
        <strong>{world.name}</strong> <span className="hint">{world.latest_version}판{world.rating === 'adult' ? ' · 성인' : ''}</span>
      </span>
      <Button variant="secondary" busy={busy} disabled={disabled} aria-label={`${world.name} 새로 시작`} onClick={onStart}>
        새로 시작
      </Button>
    </li>
  );
}

