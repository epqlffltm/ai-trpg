// web/apps/web/src/pages/story/studio/StoryWorldsStudioPage.tsx
// 내 세계관(D7, /story/studio/worlds). 최근에 고친 것부터. 마이페이지의 "만들기"와 story 첫 화면에서 온다.
// 지금(1~2단계)은 운영자만 만든다. 만들기에서 막히면 그 화면이 알린다.

import { Button, Notice } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import type { StoryWorldSummary } from '../../../api/storyWorlds';
import { formatDate } from '../../../format/dateTime';
import { NEW_WORLD_PATH, worldPath } from './worldPaths';
import { myWorldsQuery } from './worldQueries';

export function StoryWorldsStudioPage() {
  const query = useQuery(myWorldsQuery());
  const worlds = query.data?.items ?? [];
  return (
    <main className="page page--medium">
      <h1>내 세계관</h1>
      <p className="hint">story 에서 혼자 걷는 세계관을 만듭니다. 장소와 길, 물건, 인물, 이벤트, 엔딩을 채우고 게시한 판으로 세션을 시작합니다.</p>
      <p>
        <Link to={NEW_WORLD_PATH}>세계관 만들기</Link>
      </p>
      {query.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {query.isError ? (
        <Notice tone="error">
          불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void query.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      {query.isSuccess && worlds.length === 0 ? (
        <div className="empty-state">
          <p>아직 만든 세계관이 없습니다.</p>
          <Link to={NEW_WORLD_PATH}>첫 세계관 만들기</Link>
        </div>
      ) : null}
      <ul className="plain-list studio-list" aria-label="내 세계관">
        {worlds.map((world) => (
          <WorldItem key={world.id} world={world} />
        ))}
      </ul>
    </main>
  );
}

function WorldItem({ world }: { world: StoryWorldSummary }) {
  return (
    <li className="studio-list__item">
      <Link to={worldPath(world.id)}>{world.name}</Link>
      <p className="hint">
        {world.visibility === 'public' ? '공개' : '비공개'}
        {world.rating === 'adult' ? ' · 성인' : ''} · {world.latest_version === null ? '아직 게시하지 않음' : `${world.latest_version}판까지 게시`} · 고친 날{' '}
        {formatDate(world.updated_at)}
      </p>
    </li>
  );
}
