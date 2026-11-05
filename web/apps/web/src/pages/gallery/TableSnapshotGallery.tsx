// web/apps/web/src/pages/gallery/TableSnapshotGallery.tsx
// 갤러리(C7)의 TRPG 탭. 내가 그린 테이블의 장면 그림(#983)을 테이블을 넘어 최근 것부터 칸으로 늘어놓는다.
// 칸을 누르면 크게 보는 창을 열고, 창에서 저장하거나 지우거나 그 테이블로 간다. 그림은 asset 의 주소로 토큰을 실어 받는다.
// 지운 테이블의 그림도 보인다("지운 테이블"). 그 그림은 테이블로 가는 길이 없고, 여기서만 지울 수 있다.
// 지우기의 확인 단계와 경고 글은 chat·story 와 같다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useInfiniteQuery, useQueryClient, type InfiniteData, type UseInfiniteQueryResult } from '@tanstack/react-query';
import { useState } from 'react';
import { Link } from 'react-router';
import type { KeptTableSnapshot, KeptTableSnapshotPage } from '../../api/tableSnapshots';
import { saveBlob } from '../../components/saveFile';
import { formatDate } from '../../format/dateTime';
import { imageKey, useImageUrl } from '../../hooks/useImageUrl';
import { AI_IMAGE_NOTE, SNAPSHOT_DELETE_WARNING, snapshotFileName } from '../chat/conversation/snapshotsView';
import { tableSnapshotDeleteProblemText } from '../trpg/room/snapshots/tableSnapshotsView';
import { keptTableSnapshotsQuery } from './galleryQueries';
import { tablePath, tableSnapshotCaption } from './tableSnapshotGalleryView';
import { useDeleteKeptTableSnapshot } from './useDeleteKeptTableSnapshot';

export function TableSnapshotGallery() {
  const kept = useInfiniteQuery(keptTableSnapshotsQuery());
  const items = kept.data?.pages.flatMap((page) => page.items) ?? [];
  return (
    <section className="page-section" aria-labelledby="snapshot-gallery-trpg">
      <h2 id="snapshot-gallery-trpg">
        내 장면 그림 {kept.data ? <span className="hint">{kept.data.pages[0]?.total ?? 0}장</span> : null}
      </h2>
      <GalleryBody items={items} kept={kept} />
    </section>
  );
}

type BodyProps = { items: KeptTableSnapshot[]; kept: UseInfiniteQueryResult<InfiniteData<KeptTableSnapshotPage>> };

function GalleryBody({ items, kept }: BodyProps) {
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
  if (items.length === 0) return <p className="empty-state">아직 그린 장면 그림이 없습니다. 테이블 방의 라운드 아래 "장면 그림"으로 그 장면을 그립니다.</p>;
  return (
    <>
      <ul className="plain-list scene-grid" aria-label="내 장면 그림">
        {items.map((snapshot) => (
          <SnapshotTile key={snapshot.id} snapshot={snapshot} />
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

function SnapshotTile({ snapshot }: { snapshot: KeptTableSnapshot }) {
  const image = useImageUrl(snapshot.image_id);
  const [open, setOpen] = useState(false);
  const caption = tableSnapshotCaption(snapshot);
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
      {image.url ? <TableSnapshotViewer snapshot={snapshot} url={image.url} open={open} onClose={() => setOpen(false)} /> : null}
    </li>
  );
}

type ViewerProps = { snapshot: KeptTableSnapshot; url: string; open: boolean; onClose: () => void };

/** 크게 보는 창. 받아 둔 바이트를 이 기기에 저장하고(다시 받지 않는다), 그 테이블로 가거나 지운다 */
function TableSnapshotViewer({ snapshot, url, open, onClose }: ViewerProps) {
  const queryClient = useQueryClient();
  const path = tablePath(snapshot);

  function save() {
    const blob = queryClient.getQueryData<Blob>(imageKey(snapshot.image_id));
    if (blob) saveBlob(blob, snapshotFileName(snapshot.image_id, blob.type));
  }

  return (
    <Dialog title="장면 그림" open={open} onClose={onClose}>
      <img src={url} alt="장면 그림(크게)" className="chat-snapshots__large" />
      <p className="hint chat-snapshots__note">{AI_IMAGE_NOTE}</p>
      <Button variant="secondary" onClick={save}>
        이 기기에 저장
      </Button>
      {path ? <Link to={path}>그 테이블로</Link> : <p className="hint">지운 테이블의 그림입니다.</p>}
      <SnapshotDelete snapshot={snapshot} onDeleted={onClose} />
    </Dialog>
  );
}

/** 창 아래의 "지우기". 누르면 돌려받지 못한다고 알리고, "지우기 확인"을 눌러야 지운다 */
function SnapshotDelete({ snapshot, onDeleted }: { snapshot: KeptTableSnapshot; onDeleted: () => void }) {
  const removing = useDeleteKeptTableSnapshot();
  const [asking, setAsking] = useState(false);

  if (!asking) {
    return (
      <Button variant="quiet" onClick={() => setAsking(true)}>
        지우기
      </Button>
    );
  }
  return (
    <div className="chat-snapshots__delete" role="group" aria-label="장면 그림 지우기">
      <p className="hint chat-snapshots__note">{SNAPSHOT_DELETE_WARNING}</p>
      <Button variant="secondary" busy={removing.isPending} onClick={() => removing.mutate(snapshot, { onSuccess: onDeleted })}>
        지우기 확인
      </Button>
      <Button variant="quiet" disabled={removing.isPending} onClick={() => setAsking(false)}>
        그만두기
      </Button>
      {removing.error ? <p className="ui-field__error">{tableSnapshotDeleteProblemText(removing.error)}</p> : null}
    </div>
  );
}
