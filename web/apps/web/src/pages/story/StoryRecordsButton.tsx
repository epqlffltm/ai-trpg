// web/apps/web/src/pages/story/StoryRecordsButton.tsx
// 기록 창(D6, 장면의 창). 이 세계관의 엔딩(본 것은 이름·일러스트·처음 본 때, 못 본 것은 "???" 와 힌트)과
// 이 가지에서 열린 이벤트(이름과 일러스트). 계정에 남은 엔딩은 창을 열 때 받는다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useState } from 'react';
import type { StoryView } from '../../api/story';
import { formatDateTime } from '../../format/dateTime';
import { useImageUrl } from '../../hooks/useImageUrl';
import { storyEndingsQuery } from './storyQueries';
import { endingCount, endingRows, eventRows, type EndingRow } from './storyRecords';

type Props = { worldId: string; view: StoryView };

export function StoryRecordsButton({ worldId, view }: Props) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        기록
      </Button>
      <Dialog title="기록" open={open} onClose={close}>
        {open ? <Records worldId={worldId} view={view} /> : null}
      </Dialog>
    </>
  );
}

function Records({ worldId, view }: Props) {
  const records = useQuery(storyEndingsQuery(worldId));
  const endings = endingRows(view, records.data);
  const events = eventRows(view);
  const count = endingCount(view, records.data);
  return (
    <>
      <h3 className="story-records__title">엔딩{count ? <span className="hint"> · {count}</span> : null}</h3>
      {records.isError ? <p className="hint">처음 본 때를 불러오지 못했습니다.</p> : null}
      {endings.length === 0 ? <p className="empty-state">이 세계관에는 엔딩이 없습니다.</p> : null}
      <ul className="plain-list story-records" aria-label="엔딩">
        {endings.map((ending) => (
          <EndingItem key={ending.id} ending={ending} />
        ))}
      </ul>
      <h3 className="story-records__title">열린 이벤트</h3>
      {events.length === 0 ? <p className="empty-state">아직 열린 이벤트가 없습니다.</p> : null}
      <ul className="plain-list story-records" aria-label="열린 이벤트">
        {events.map((event) => (
          <li key={event.id} className="story-records__row">
            <Thumb imageId={event.imageId} alt={event.name} />
            <span>{event.name}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function EndingItem({ ending }: { ending: EndingRow }) {
  return (
    <li className="story-records__row">
      <Thumb imageId={ending.imageId} alt={ending.name} />
      <span>
        {ending.name}
        {ending.seen ? null : <span className="hint story-places__detail">{ending.hint || '힌트가 없습니다.'}</span>}
        {ending.firstSeenAt ? (
          <span className="hint story-places__detail">
            처음 본 때 <time dateTime={ending.firstSeenAt}>{formatDateTime(ending.firstSeenAt)}</time>
          </span>
        ) : null}
        {ending.counted ? null : <span className="hint story-places__detail">기록에 남지 않는 엔딩</span>}
      </span>
    </li>
  );
}

function Thumb({ imageId, alt }: { imageId: string | null; alt: string }) {
  const image = useImageUrl(imageId);
  return image.url ? <img src={image.url} alt={alt} className="story-records__image" /> : <span className="story-records__image" aria-hidden="true" />;
}
