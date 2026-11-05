// web/apps/web/src/pages/trpg/room/host/HostPanel.tsx
// 방장의 운영(B6 의 ⑤, Stitch 20번의 "테이블 관리"). 방장에게만, 테이블 줄의 "테이블 관리"를 눌렀을 때 그 아래에 펼친다.
// 사람(내보내기, 방장 넘기기, 한 번 더 굴리기), 서술 모델과 단계(B8), 진행의 설정, 테이블 끝내기.
// 창(Dialog)으로 띄우지 않는다. 내보내기와 끝내기가 한 번 더 묻는 창(ConfirmButton)을 열어 창이 겹치기 때문이다.
// 시작과 라운드 닫기는 그 자리(대기실, 지금 라운드)에 있다. 결과를 정하는 임시 권한(#367)은 넣지 않는다.

import { endTable } from '../../../../api/tableHost';
import type { TableDetail } from '../../../../api/types';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { MemberActions } from './MemberActions';
import { ModelSettings } from './ModelSettings';
import { TableSettings } from './TableSettings';
import { useHostAction } from './useHostAction';

type Props = { table: TableDetail; myId: string | undefined; nameOfMember: (userId: string) => string };

/** 테이블 관리를 할 수 있는가. 방장이고 테이블이 끝나지 않았을 때다 */
export function canManageTable(table: TableDetail, myId: string | undefined): boolean {
  return table.status !== 'ended' && myId !== undefined && table.host_id === myId;
}

export const HOST_PANEL_ID = 'table-manage';

export function HostPanel({ table, myId, nameOfMember }: Props) {
  if (!canManageTable(table, myId)) return null;
  return (
    <section id={HOST_PANEL_ID} className="room-panel host-panel" aria-labelledby="host-panel-heading">
      <h2 id="host-panel-heading">테이블 관리</h2>
      <div className="host-panel__columns">
        <div>
          <h3 className="waiting-room__label">앉은 사람</h3>
          <MemberActions table={table} myId={myId} nameOfMember={nameOfMember} />
        </div>
        <div>
          <h3 className="waiting-room__label">진행</h3>
          <ModelSettings table={table} />
          <TableSettings table={table} />
          <EndTable table={table} />
        </div>
      </div>
    </section>
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
