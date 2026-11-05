// web/apps/web/src/pages/trpg/room/snapshots/RoundSnapshots.tsx
// 라운드의 장면 아래의 장면 그림(#983). 그 라운드의 그림들과 그리는 중·실패의 표시, 그리고 "장면 그림" 단추.
// 누가 그렸든 앉은 사람 모두가 본다. 값은 누른 사람이 낸다. 그림의 바이트는 게임 서버가 대신 내준다(토큰을 실어 받는다).
// 그림 아래에 "AI 가 만든 그림"을 적는다. 그림을 누르면 크게 보는 창을 열고, 창에서 이 기기에 저장한다(받아 둔 바이트로).
// 내가 그린 그림이면 창 아래에 "지우기"를 두고, 한 번 더 확인한 뒤 지운다(돌려받지 못한다고 알린다). 지우면 창을 닫는다.
// 글과 고르기는 tableSnapshotsView.ts, 단추와 지우기 경고의 글은 chat·story 의 것과 같다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { fetchTableSnapshotImage, type TableSnapshot } from '../../../../api/tableSnapshots';
import { saveBlob } from '../../../../components/saveFile';
import {
  canOfferSnapshot,
  SNAPSHOT_DELETE_WARNING,
  snapshotButtonHint,
  snapshotButtonLabel,
  snapshotFailureText,
} from '../../../chat/conversation/snapshotsView';
import {
  snapshotCaption,
  snapshotsOfRound,
  tableSnapshotDeleteProblemText,
  tableSnapshotFileName,
  tableSnapshotProblemText,
} from './tableSnapshotsView';
import { useDeleteTableSnapshot } from './useDeleteTableSnapshot';
import type { TableSnapshotsSource } from './useTableSnapshots';

type Props = { tableId: string; roundNumber: number; scene: string; source: TableSnapshotsSource };

/** 그 라운드의 그림들과 단추. 장면의 글이 없으면 아무것도 그리지 않는다 */
export function RoundSnapshots({ tableId, roundNumber, scene, source }: Props) {
  if (!scene.trim()) return null;
  const snapshots = snapshotsOfRound(source.list, roundNumber);
  const tried = source.draw.variables === roundNumber;
  return (
    <div className="chat-snapshots" aria-label={`라운드 ${roundNumber}의 장면 그림`}>
      {snapshots.map((snapshot) => (
        <SnapshotItem key={snapshot.id} tableId={tableId} snapshot={snapshot} />
      ))}
      {canOfferSnapshot(source.price) ? (
        <Button variant="quiet" disabled={source.blocked} title={snapshotButtonHint(source.price)} onClick={() => source.draw.mutate(roundNumber)}>
          {snapshotButtonLabel(source.price)}
        </Button>
      ) : null}
      {tried && source.draw.error ? <p className="ui-field__error chat-snapshots__note">{tableSnapshotProblemText(source.draw.error)}</p> : null}
    </div>
  );
}

function SnapshotItem({ tableId, snapshot }: { tableId: string; snapshot: TableSnapshot }) {
  if (snapshot.status === 'drawing') return <p className="hint chat-snapshots__note">장면 그림을 그리는 중…</p>;
  if (snapshot.status === 'failed') return <p className="ui-field__error chat-snapshots__note">{snapshotFailureText(snapshot.code)}</p>;
  return <SnapshotImage tableId={tableId} snapshot={snapshot} />;
}

/** 다 그린 그림 하나를 받아 띄울 주소(blob:)로 바꾼다. 그림은 바뀌지 않으므로 한 번 받은 것은 다시 받지 않는다 */
function useSnapshotImage(tableId: string, snapshotId: string): { blob: Blob | undefined; url: string | null; failed: boolean } {
  const query = useQuery({
    queryKey: ['trpg', 'tables', tableId, 'snapshot-image', snapshotId] as const,
    queryFn: ({ signal }) => fetchTableSnapshotImage(tableId, snapshotId, signal),
    staleTime: Infinity,
  });
  const blob = query.data;
  const url = useMemo(() => (blob && blob.size > 0 ? URL.createObjectURL(blob) : null), [blob]);
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);
  return { blob, url, failed: query.isError };
}

function SnapshotImage({ tableId, snapshot }: { tableId: string; snapshot: TableSnapshot }) {
  const image = useSnapshotImage(tableId, snapshot.id);
  const [viewing, setViewing] = useState(false);
  if (image.failed) return <p className="hint chat-snapshots__note">그림을 받지 못했습니다.</p>;
  if (!image.url) return null;
  const caption = snapshotCaption(snapshot);

  function save() {
    if (image.blob) saveBlob(image.blob, tableSnapshotFileName(snapshot, image.blob.type));
  }

  return (
    <figure className="chat-snapshots__figure">
      <button type="button" className="chat-snapshots__open" aria-label="장면 그림 크게 보기" onClick={() => setViewing(true)}>
        <img src={image.url} alt="장면 그림" className="chat-snapshots__image" />
      </button>
      <figcaption className="hint chat-snapshots__note">{caption}</figcaption>
      <Dialog title="장면 그림" open={viewing} onClose={() => setViewing(false)}>
        <img src={image.url} alt="장면 그림(크게)" className="chat-snapshots__large" />
        <p className="hint chat-snapshots__note">{caption}</p>
        <Button variant="secondary" onClick={save}>
          이 기기에 저장
        </Button>
        {snapshot.by_me ? <SnapshotDelete tableId={tableId} snapshotId={snapshot.id} onDeleted={() => setViewing(false)} /> : null}
      </Dialog>
    </figure>
  );
}

type DeleteProps = { tableId: string; snapshotId: string; onDeleted: () => void };

/** 창 아래의 "지우기". 누르면 돌려받지 못한다고 알리고, "지우기 확인"을 눌러야 지운다. 내가 그린 그림에만 둔다 */
function SnapshotDelete({ tableId, snapshotId, onDeleted }: DeleteProps) {
  const removing = useDeleteTableSnapshot(tableId);
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
      {removing.error ? <p className="ui-field__error">{tableSnapshotDeleteProblemText(removing.error)}</p> : null}
    </div>
  );
}
