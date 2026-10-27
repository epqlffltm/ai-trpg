// web/apps/web/src/pages/story/StoryWorldPage.tsx
// 세계관 소개(D1, /story/worlds/:worldId). 로그인하지 않아도 전체이용가면 보인다. 볼 수 없으면(내렸다, 등급, 없다) 서버는 모두 404 다.
// 머리(대표 그림, 이름, 등급·기한·태그), 제작자가 꾸민 소개(거른 HTML), 인물(보임: 이름과 그림, 실루엣: "???", 숨김은 오지 않는다),
// 엔딩("엔딩 2/5", 본 수는 로그인했을 때), 내 세션(이 세계관의 것), 새로 시작(로그인하지 않았으면 로그인으로).

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useParams } from 'react-router';
import { ApiError } from '../../api/errors';
import type { PublicCastMember, PublicWorldDetail } from '../../api/storyWorlds';
import { useSession } from '../../auth/useSession';
import { formatDateTime } from '../../format/dateTime';
import { useImageUrl } from '../../hooks/useImageUrl';
import { IntroHtml } from '../chat/character/IntroHtml';
import { publicWorldQuery, storyEndingsQuery, worldSessionsQuery } from './storyQueries';
import { describeStartProblem } from './storyTurnProblem';
import { castLabel, endingLine, worldTags } from './storyWorldView';
import { useStartStorySession } from './useStartStorySession';

export function StoryWorldPage() {
  const { worldId = '' } = useParams();
  const signedIn = useSession() !== null;
  const query = useQuery(publicWorldQuery(worldId, signedIn));

  if (query.isPending) return <p className="page page--loading">불러오는 중</p>;
  if (query.isError) return <LoadProblem error={query.error} onRetry={() => void query.refetch()} />;
  return <WorldDetail world={query.data} signedIn={signedIn} />;
}

function WorldDetail({ world, signedIn }: { world: PublicWorldDetail; signedIn: boolean }) {
  const image = useImageUrl(world.image_id);
  const endings = useQuery(storyEndingsQuery(world.id, signedIn));
  const line = endingLine(world.ending_count, signedIn ? (endings.data?.items.length ?? null) : null);
  return (
    <main className="page page--medium story-world">
      <p>
        <Link to="/story">story</Link>
      </p>
      <header className="story-world__head">
        {image.url ? <img src={image.url} alt="" className="story-world__image" /> : null}
        <h1>{world.name}</h1>
        <p className="hint">
          {[...worldTags(world), `${world.version}판`, world.after_ending === 'epilogue' ? '엔딩 뒤 후일담' : null].filter(Boolean).join(' · ')}
        </p>
        {line ? <p>{line}</p> : null}
      </header>
      <section aria-labelledby="world-intro">
        <h2 id="world-intro">소개</h2>
        <IntroHtml html={world.intro_html} />
      </section>
      {world.cast.length > 0 ? (
        <section aria-labelledby="world-cast">
          <h2 id="world-cast">인물</h2>
          <ul className="plain-list story-world__cast" aria-label="인물">
            {world.cast.map((member) => (
              <CastCard key={member.id} member={member} />
            ))}
          </ul>
        </section>
      ) : null}
      <StartSection worldId={world.id} signedIn={signedIn} />
    </main>
  );
}

function CastCard({ member }: { member: PublicCastMember }) {
  const image = useImageUrl(member.reveal === 'shown' ? member.image_id : null);
  return (
    <li className={member.reveal === 'silhouette' ? 'story-world__member story-world__member--silhouette' : 'story-world__member'}>
      {image.url ? <img src={image.url} alt="" className="story-world__portrait" /> : <span className="story-world__portrait" aria-hidden="true" />}
      <span>{castLabel(member)}</span>
    </li>
  );
}

function StartSection({ worldId, signedIn }: { worldId: string; signedIn: boolean }) {
  const location = useLocation();
  const sessions = useQuery(worldSessionsQuery(worldId, signedIn));
  const starting = useStartStorySession();
  if (!signedIn) {
    return (
      <section className="page-section" aria-labelledby="world-start">
        <h2 id="world-start">시작하기</h2>
        <p>
          <Link to="/login" state={{ from: location.pathname }}>
            로그인
          </Link>
          하면 이 세계관으로 이야기를 시작합니다.
        </p>
      </section>
    );
  }
  const items = sessions.data?.items ?? [];
  return (
    <section className="page-section" aria-labelledby="world-start">
      <h2 id="world-start">내 세션</h2>
      {sessions.isSuccess && items.length === 0 ? <p className="hint">처음 시작합니다.</p> : null}
      <ul className="plain-list story-sessions" aria-label="이 세계관의 내 세션">
        {items.map((session) => (
          <li key={session.id} className="story-sessions__row">
            <Link to={`/story/sessions/${encodeURIComponent(session.id)}`}>
              {session.world.version}판 · <time dateTime={session.updated_at}>{formatDateTime(session.updated_at)}</time>
            </Link>
          </li>
        ))}
      </ul>
      {starting.error ? <Notice tone="error">{describeStartProblem(starting.error)}</Notice> : null}
      <Button busy={starting.isPending} onClick={() => starting.mutate(worldId)}>
        새로 시작
      </Button>
    </section>
  );
}

function LoadProblem({ error, onRetry }: { error: Error; onRetry: () => void }) {
  // 경로의 ID 가 UUID 가 아니면 422 다. 없는 것과 같게 본다
  const missing = error instanceof ApiError && (error.status === 404 || error.status === 422);
  return (
    <main className="page page--narrow">
      <h1>세계관</h1>
      {missing ? (
        <Notice>볼 수 없는 세계관입니다.</Notice>
      ) : (
        <Notice tone="error">
          세계관을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={onRetry}>
            다시 시도
          </Button>
        </Notice>
      )}
      <Link to="/story">다른 세계관 찾기</Link>
    </main>
  );
}
