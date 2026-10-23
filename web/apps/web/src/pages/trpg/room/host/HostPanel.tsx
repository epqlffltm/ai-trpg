// web/apps/web/src/pages/trpg/room/host/HostPanel.tsx
// 방장의 운영(B6 의 ⑤). 방장에게만 보인다. 접어 둔다. 사람(내보내기, 방장 넘기기, 한 번 더 굴리기), 진행의 설정, 테이블 끝내기.
// 시작과 라운드 닫기는 그 자리(대기실, 지금 라운드)에 있다. 서술 모델(B8)과 결과를 정하는 임시 권한(#367)은 넣지 않는다.

import { endTable } from '../../../../api/tableHost';
import type { TableDetail } from '../../../../api/types';
import { ConfirmButton } from './ConfirmButton';
import { MemberActions } from './MemberActions';
import { TableSettings } from './TableSettings';
import { useHostAction } from './useHostAction';

type Props = { table: TableDetail; myId: string | undefined; nameOfMember: (userId: string) => string };

export function HostPanel({ table, myId, nameOfMember }: Props) {
  if (table.status === 'ended' || myId === undefined || table.host_id !== myId) return null;
  return (
    <details className="room-panel host-panel">
      <summary>
        <h2 className="host-panel__title">방장</h2>
      </summary>
      <h3 className="waiting-room__label">앉은 사람</h3>
      <MemberActions table={table} myId={myId} nameOfMember={nameOfMember} />
      <h3 className="waiting-room__label">진행</h3>
      <TableSettings table={table} />
      <EndTable table={table} />
    </details>
  );
}

function EndTable({ table }: { table: TableDetail }) {
  const action = useHostAction(table.id);
  return (
    <div className="host-end">
      <ConfirmButton
        label="테이블 끝내기"
        title="테이블 끝내기"
        confirm="끝내기"
        variant="secondary"
        busy={action.busy}
        problem={action.problem}
        onConfirm={async () => (await action.run(() => endTable(table.id))) !== null}
      >
        <p>테이블을 끝냅니다. 되돌릴 수 없습니다. 끝난 테이블은 읽기만 할 수 있고, 채팅도 쓸 수 없습니다.</p>
      </ConfirmButton>
    </div>
  );
}
