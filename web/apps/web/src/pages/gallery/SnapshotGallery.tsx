// web/apps/web/src/pages/gallery/SnapshotGallery.tsx
// 갤러리(C7)의 "내 장면 그림"(#983). 그 서비스에서 내가 그린 장면 그림을 최근 것부터 칸으로 늘어놓는다.
// 칸을 누르면 크게 보는 창(대화의 것과 같다)을 열고, 창에서 저장하거나 지우거나 그 대화로 간다. 그림은 토큰을 실어 받는다.
// 지운 대화의 그림은 서버가 싣지 않는다. 읽지 못하면 이 칸만 실패를 알린다(아래의 일러스트는 따로 돈다).

import { Button } from '@ai-trpg/ui';
import { useInfiniteQuery, type InfiniteData, type UseInfiniteQueryResult } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { KeptSnapshot, KeptSnapshotPage, SnapshotService } from '../../api/snapshots';
import { formatDate } from '../../format/dateTime';
import { useImageUrl } from '../../hooks/useImageUrl';
import { SnapshotViewer } from '../chat/conversation/MessageSnapshots';
import { AI_IMAGE_NOTE } from '../chat/conversation/snapshotsView';
import { keptSnapshotsQuery } from './galleryQueries';
import { conversationLinkLabel, conversationPath, snapshotCaption } from './snapshotGalleryView';

export function SnapshotGallery({ service }: { service: SnapshotService }) {
  const kept = useInfiniteQuery(keptSnapshotsQuery(service));
  const items = kept.data?.pages.flatMap((page) => page.items) ?? [];
  const heading = `snapshot-gallery-${service}`;
  return (
    <section className="page-section" aria-labelledby={heading}>
      <h2 id={heading}>
        내 장면 그림 {kept.data ? <span className="hint">{kept.data.pages[0]?.total ?? 0}장</span> : null}
      </h2>
      <SnapshotGalleryBody service={service} items={items} kept={kept} />
    </section>
  );
}

type BodyProps = { service: SnapshotService; items: KeptSnapshot[]; kept: UseInfiniteQueryResult<InfiniteData<KeptSnapshotPage>> };

function SnapshotGalleryBody({ service, items, kept }: BodyProps) {
  if (kept.isPending) return <p aria-busy="true">불러오는 중</p>;
  if (kept.isError && !kept.data) {
    return (
      <p className="hint">
        장면 그림을 불러오지 못했습니다.{' '}
        <Button variant="quiet" onClick={() => void kept.refetch()}>
          장면 그림 다시 불러오기
        </Button>
      </p>
    );
  }
  if (items.length === 0) return <p className="empty-state">아직 그린 장면 그림이 없습니다. 답 아래의 "장면 그림"으로 그 장면을 그립니다.</p>;
  return (
    <>
      <ul className="plain-list scene-grid" aria-label="내 장면 그림">
        {items.map((snapshot) => (
          <SnapshotTile key={snapshot.id} service={service} snapshot={snapshot} />
        ))}
      </ul>
      {kept.hasNextPage ? (
        <div className="load-more">
          <Button variant="secondary" busy={kept.isFetchingNextPage} onClick={() => void kept.fetchNextPage()}>
            장면 그림 더 보기
          </Button>
        </div>
      ) : null}
    </>
  );
}

function SnapshotTile({ service, snapshot }: { service: SnapshotService; snapshot: KeptSnapshot }) {
  const image = useImageUrl(snapshot.image_id);
  const [open, setOpen] = useState(false);
  const caption = snapshotCaption(snapshot);
  const picture = image.url ? <img src={image.url} alt={`장면 그림: ${caption}`} className="scene-tile__image" /> : <div className="scene-tile__image scene-tile__image--empty" aria-hidden="true" />;
  return (
    <li className="scene-tile">
      <Button variant="quiet" aria-label={`${caption} 장면 그림 크게 보기`} disabled={!image.url} onClick={() => setOpen(true)}>
        {picture}
      </Button>
      <p className="scene-tile__title">{caption}</p>
      <p className="hint">
        {formatDate(snapshot.created_at)} · {AI_IMAGE_NOTE}
      </p>
      {image.url ? (
        <SnapshotViewer service={service} snapshotId={snapshot.id} imageId={snapshot.image_id} url={image.url} open={open} onClose={() => setOpen(false)}>
          <Link to={conversationPath(service, snapshot.conversation_id)}>{conversationLinkLabel(service)}</Link>
        </SnapshotViewer>
      ) : null}
    </li>
  );
}
