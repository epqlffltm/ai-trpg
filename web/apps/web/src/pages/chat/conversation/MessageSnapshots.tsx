// web/apps/web/src/pages/chat/conversation/MessageSnapshots.tsx
// 말 아래의 장면 그림(#983). 그 말의 그림들과 그리는 중·실패의 표시, 그리고 "장면 그림" 단추.
// chat 의 말과 story 의 말이 함께 쓴다. 그림은 토큰을 실어 받는다(useImageUrl).

import { Button } from '@ai-trpg/ui';
import type { Snapshot, SnapshotPrice } from '../../../api/snapshots';
import { useImageUrl } from '../../../hooks/useImageUrl';
import { snapshotButtonHint, snapshotButtonLabel, snapshotFailureText } from './snapshotsView';

/** 그 말의 그림들. 없으면 아무것도 그리지 않는다 */
export function MessageSnapshots({ snapshots }: { snapshots: Snapshot[] }) {
  if (snapshots.length === 0) return null;
  return (
    <div className="chat-snapshots" aria-label="장면 그림">
      {snapshots.map((snapshot) => (
        <SnapshotItem key={snapshot.id} snapshot={snapshot} />
      ))}
    </div>
  );
}

function SnapshotItem({ snapshot }: { snapshot: Snapshot }) {
  if (snapshot.status === 'drawing') return <p className="hint chat-snapshots__note">장면 그림을 그리는 중…</p>;
  if (snapshot.status === 'failed') return <p className="ui-field__error chat-snapshots__note">{snapshotFailureText(snapshot.code)}</p>;
  return <SnapshotImage imageId={snapshot.image_id} />;
}

function SnapshotImage({ imageId }: { imageId: string | null }) {
  const image = useImageUrl(imageId);
  if (image.failed) return <p className="hint chat-snapshots__note">그림을 받지 못했습니다.</p>;
  if (!image.url) return null;
  return <img src={image.url} alt="장면 그림" className="chat-snapshots__image" />;
}

type ButtonProps = { price: SnapshotPrice | undefined; disabled: boolean; onDraw: () => void };

/** 그 답을 장면 그림으로 그리는 단추. 값을 알면 글에 싣는다("장면 그림 · 160") */
export function SnapshotButton({ price, disabled, onDraw }: ButtonProps) {
  return (
    <Button variant="quiet" disabled={disabled} title={snapshotButtonHint(price)} onClick={onDraw}>
      {snapshotButtonLabel(price)}
    </Button>
  );
}
