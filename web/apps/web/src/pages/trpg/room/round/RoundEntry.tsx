// web/apps/web/src/pages/trpg/room/round/RoundEntry.tsx
// 지나간 라운드 하나. 그 라운드를 연 장면(GM 의 서술)과, 그 라운드의 선언과 결과.
// 다음 라운드의 장면이 이 라운드의 결과를 서술한 글이다. 장면 아래에 그 라운드의 장면 그림(#983)을 둔다.

import type { Round, TableDetail } from '../../../../api/types';
import { RoundSnapshots } from '../snapshots/RoundSnapshots';
import type { TableSnapshotsSource } from '../snapshots/useTableSnapshots';
import { DeclarationList } from './DeclarationList';

type Props = { round: Round; table: TableDetail; snapshots: TableSnapshotsSource };

export function RoundEntry({ round, table, snapshots }: Props) {
  return (
    <article className="round" aria-labelledby={`round-${round.number}`}>
      <h3 id={`round-${round.number}`} className="round__number">
        라운드 {round.number}
      </h3>
      <p className="prose scene">{round.scene}</p>
      <RoundSnapshots tableId={table.id} roundNumber={round.number} scene={round.scene} source={snapshots} />
      <DeclarationList round={round} table={table} />
    </article>
  );
}
