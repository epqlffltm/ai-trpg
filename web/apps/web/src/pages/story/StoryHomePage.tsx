// web/apps/web/src/pages/story/StoryHomePage.tsx
// 내 이야기(D, /story). 로그인해야 열린다. 위에 내 세션(최근 것부터, 20 개씩 "더 보기"), 아래에 새로 시작할 세계관.
// 새로 시작은 지금은 내 세계관(게시한 판이 있는 것)만이다. 남에게 공개된 세계관의 목록은 asset 서버에 아직 없다(D1 은 그때 만든다).
// 시작하면 세계관의 마지막 판을 고정한 새 세션이 생기고 장면(D2)으로 간다. 모델은 지난번 세션의 것이다.

import { Button, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router';
import { startStorySession, type StorySessionSummary } from '../../api/story';
import type { StoryWorldSummary } from '../../api/storyWorlds';
import { formatDateTime } from '../../format/dateTime';
import { myStoryWorldsQuery, STORY_SESSIONS_KEY, storySessionKey, storySessionsQuery } from './storyQueries';
import { describeStartProblem } from './storyTurnProblem';

export function StoryHomePage() {
  return (
    <main className="page page--medium">
      <h1>내 이야기</h1>
      <p className="hint">세계관 하나를 걸으며 여러 인물을 만나는 이야기입니다. 세션마다 그때의 판으로 돕니다.</p>
      <MySessions />
      <StartFromMyWorlds />
    </main>
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
        {session.world.name} {session.world.version}판 · {session.model?.display_name ?? '모델 없음'} · <time dateTime={session.updated_at}>{formatDateTime(session.updated_at)}</time>
      </p>
    </li>
  );
}

function StartFromMyWorlds() {
  const worlds = useQuery(myStoryWorldsQuery());
  const starting = useStart();
  const startable = (worlds.data?.items ?? []).filter((world) => world.latest_version !== null);
  return (
    <section className="page-section" aria-labelledby="story-start">
      <h2 id="story-start">새로 시작</h2>
      <p className="hint">내가 만들어 게시한 세계관으로 시작합니다.</p>
      {worlds.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {worlds.isError ? <Notice tone="error">세계관을 불러오지 못했습니다. 잠시 뒤에 다시 열어 주세요.</Notice> : null}
      {worlds.isSuccess && startable.length === 0 ? <p className="empty-state">게시한 세계관이 없습니다.</p> : null}
      {starting.error ? <Notice tone="error">{describeStartProblem(starting.error)}</Notice> : null}
      <ul className="plain-list story-worlds" aria-label="시작할 세계관">
        {startable.map((world) => (
          <WorldRow key={world.id} world={world} busy={starting.isPending && starting.variables === world.id} disabled={starting.isPending} onStart={() => starting.mutate(world.id)} />
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

/** 새 세션을 만들고 장면으로 간다. 받은 세션을 넣어 두어 다시 읽지 않는다 */
function useStart() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: (worldId: string) => startStorySession(worldId),
    onSuccess: async (session) => {
      queryClient.setQueryData(storySessionKey(session.id), session);
      await queryClient.invalidateQueries({ queryKey: STORY_SESSIONS_KEY });
      void navigate(`/story/sessions/${encodeURIComponent(session.id)}`);
    },
  });
}
