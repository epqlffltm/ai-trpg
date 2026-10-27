// web/apps/web/src/pages/gallery/StoryGallery.tsx
// 갤러리(C7)의 story 탭. 내 세션의 세계관마다 연 일러스트(이벤트와 엔딩의 장면)를 인물마다 묶어 늘어놓는다.
// 세계관은 내 세션의 목록에서 모은다(세션을 더 읽으면 세계관이 늘어난다). 세계관마다 story 서버의 갤러리를 따로 부르고 따로 실패한다.
// 서버는 연 것만 보낸다(열지 않은 칸은 없다). 장면의 이름은 오지 않아 종류(이벤트, 엔딩)와 연 날을 적는다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import { Link } from 'react-router';
import { formatDate } from '../../format/dateTime';
import { useImageUrl } from '../../hooks/useImageUrl';
import { publicWorldQuery, storyGalleryQuery, storySessionsQuery } from '../story/storyQueries';
import { groupIllustrations, sessionWorlds, type IllustrationCell, type StoryWorldEntry } from './storyGalleryView';

export function StoryGallery() {
  const sessions = useInfiniteQuery(storySessionsQuery());
  const worlds = sessionWorlds(sessions.data?.pages.flatMap((page) => page.items) ?? []);
  if (sessions.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (sessions.isError && !sessions.data) {
    return (
      <Notice tone="error">
        내 세션을 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void sessions.refetch()}>
          다시 시도
        </Button>
      </Notice>
    );
  }
  return (
    <>
      {worlds.length === 0 ? (
        <p className="empty-state">
          아직 걸어 본 세계관이 없습니다. <Link to="/story">세계관을 골라</Link> 이야기를 시작해 보세요.
        </p>
      ) : null}
      {worlds.map((world) => (
        <WorldGallery key={world.id} world={world} />
      ))}
      {sessions.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={sessions.isFetchingNextPage} onClick={() => void sessions.fetchNextPage()}>
            세계관 더 보기
          </Button>
        </div>
      ) : null}
    </>
  );
}

function WorldGallery({ world }: { world: StoryWorldEntry }) {
  const gallery = useQuery(storyGalleryQuery(world.id));
  const detail = useQuery(publicWorldQuery(world.id, true));
  const groups = groupIllustrations(gallery.data?.items ?? [], detail.data?.cast);
  const heading = `story-gallery-${world.id}`;
  return (
    <section className="page-section" aria-labelledby={heading}>
      <h2 id={heading}>
        <Link to={`/story/worlds/${world.id}`}>{world.name}</Link>
        {gallery.data ? <span className="hint"> {gallery.data.items.length}개 열림</span> : null}
      </h2>
      {gallery.isPending ? <p className="hint">불러오는 중</p> : null}
      {gallery.isError ? (
        <p className="hint">
          갤러리를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void gallery.refetch()}>
            다시 시도
          </Button>
        </p>
      ) : null}
      {gallery.data && groups.length === 0 ? <p className="empty-state">아직 연 일러스트가 없습니다.</p> : null}
      {groups.map((group) => (
        <div key={group.key}>
          <h3 className="story-records__title">{group.title}</h3>
          <ul className="plain-list scene-grid" aria-label={`${world.name} · ${group.title}의 장면`}>
            {group.cells.map((cell) => (
              <IllustrationTile key={cell.key} cell={cell} />
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

function IllustrationTile({ cell }: { cell: IllustrationCell }) {
  const image = useImageUrl(cell.imageId);
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const label = `${cell.title} 장면`;
  return (
    <li className="scene-tile">
      <Button variant="quiet" aria-label={`${label} 크게 보기`} onClick={() => setOpen(true)}>
        {image.url ? <img src={image.url} alt={label} className="scene-tile__image" /> : <div className="scene-tile__image scene-tile__image--empty" aria-hidden="true" />}
      </Button>
      <p className="scene-tile__title">{cell.title}</p>
      <p className="hint">{formatDate(cell.firstSeenAt)}</p>
      <Dialog title={label} open={open} onClose={close}>
        {image.url ? <img src={image.url} alt={label} className="scene-tile__large" /> : <p className="hint">그림을 불러오지 못했습니다.</p>}
      </Dialog>
    </li>
  );
}
