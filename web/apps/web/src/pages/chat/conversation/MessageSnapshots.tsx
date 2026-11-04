// web/apps/web/src/pages/chat/conversation/MessageSnapshots.tsx
// 말 아래의 장면 그림(#983). 그 말의 그림들과 그리는 중·실패의 표시, 그리고 "장면 그림" 단추.
// chat 의 말과 story 의 말이 함께 쓴다. 그림은 토큰을 실어 받는다(useImageUrl).
// 그림 아래에 "AI 가 만든 그림"을 적는다. 그림을 누르면 크게 보는 창을 열고, 창에서 이 기기에 저장한다(받아 둔 바이트로).
// 창의 "지우기"는 한 번 더 확인한 뒤 지운다(돌려받지 못한다고 알린다). 지우면 창을 닫고 목록을 다시 읽는다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import type { Snapshot, SnapshotPrice, SnapshotService } from '../../../api/snapshots';
import { saveBlob } from '../../../components/saveFile';
import { imageKey, useImageUrl } from '../../../hooks/useImageUrl';
import {
  AI_IMAGE_NOTE,
  SNAPSHOT_DELETE_WARNING,
  snapshotButtonHint,
  snapshotButtonLabel,
  snapshotDeleteProblemText,
  snapshotFailureText,
  snapshotFileName,
} from './snapshotsView';
import { useDeleteSnapshot } from './useDeleteSnapshot';

/** 그 말의 그림들. 없으면 아무것도 그리지 않는다 */
export function MessageSnapshots({ service, snapshots }: { service: SnapshotService; snapshots: Snapshot[] }) {
  if (snapshots.length === 0) return null;
  return (
    <div className="chat-snapshots" aria-label="장면 그림">
      {snapshots.map((snapshot) => (
        <SnapshotItem key={snapshot.id} service={service} snapshot={snapshot} />
      ))}
    </div>
  );
}

function SnapshotItem({ service, snapshot }: { service: SnapshotService; snapshot: Snapshot }) {
  if (snapshot.status === 'drawing') return <p className="hint chat-snapshots__note">장면 그림을 그리는 중…</p>;
  if (snapshot.status === 'failed') return <p className="ui-field__error chat-snapshots__note">{snapshotFailureText(snapshot.code)}</p>;
  return <SnapshotImage service={service} snapshotId={snapshot.id} imageId={snapshot.image_id} />;
}

function SnapshotImage({ service, snapshotId, imageId }: { service: SnapshotService; snapshotId: string; imageId: string | null }) {
  const image = useImageUrl(imageId);
  const [viewing, setViewing] = useState(false);
  if (image.failed) return <p className="hint chat-snapshots__note">그림을 받지 못했습니다.</p>;
  if (!image.url || imageId === null) return null;
  return (
    <figure className="chat-snapshots__figure">
      <button type="button" className="chat-snapshots__open" aria-label="장면 그림 크게 보기" onClick={() => setViewing(true)}>
        <img src={image.url} alt="장면 그림" className="chat-snapshots__image" />
      </button>
      <figcaption className="hint chat-snapshots__note">{AI_IMAGE_NOTE}</figcaption>
      <SnapshotViewer service={service} snapshotId={snapshotId} imageId={imageId} url={image.url} open={viewing} onClose={() => setViewing(false)} />
    </figure>
  );
}

type ViewerProps = {
  service: SnapshotService;
  snapshotId: string;
  imageId: string;
  url: string;
  open: boolean;
  onClose: () => void;
  children?: ReactNode;
};

/** 장면 그림을 크게 보는 창. 받아 둔 바이트를 이 기기에 저장한다(다시 받지 않는다). 갤러리(C7)도 쓴다. children 은 창 아래에 더할 것이다 */
export function SnapshotViewer({ service, snapshotId, imageId, url, open, onClose, children }: ViewerProps) {
  const queryClient = useQueryClient();

  function save() {
    const blob = queryClient.getQueryData<Blob>(imageKey(imageId));
    if (blob) saveBlob(blob, snapshotFileName(imageId, blob.type));
  }

  return (
    <Dialog title="장면 그림" open={open} onClose={onClose}>
      <img src={url} alt="장면 그림(크게)" className="chat-snapshots__large" />
      <p className="hint chat-snapshots__note">{AI_IMAGE_NOTE}</p>
      <Button variant="secondary" onClick={save}>
        이 기기에 저장
      </Button>
      {children}
      <SnapshotDelete service={service} snapshotId={snapshotId} onDeleted={onClose} />
    </Dialog>
  );
}

type DeleteProps = { service: SnapshotService; snapshotId: string; onDeleted: () => void };

/** 창 아래의 "지우기". 누르면 돌려받지 못한다고 알리고, "지우기 확인"을 눌러야 지운다 */
function SnapshotDelete({ service, snapshotId, onDeleted }: DeleteProps) {
  const removing = useDeleteSnapshot(service);
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
      <Button variant="secondary" busy={removing.isPending} onClick={() => removing.mutate(snapshotId, { onSuccess: onDeleted })}>
        지우기 확인
      </Button>
      <Button variant="quiet" disabled={removing.isPending} onClick={() => setAsking(false)}>
        그만두기
      </Button>
      {removing.error ? <p className="ui-field__error">{snapshotDeleteProblemText(removing.error)}</p> : null}
    </div>
  );
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
