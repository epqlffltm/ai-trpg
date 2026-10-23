// web/apps/web/src/pages/trpg/room/round/RoundEntry.tsx
// 지나간 라운드 하나. 그 라운드를 연 장면(GM 의 서술)과, 그 라운드의 선언과 결과.
// 다음 라운드의 장면이 이 라운드의 결과를 서술한 글이다.

import type { Round, TableDetail } from '../../../../api/types';
import { DeclarationList } from './DeclarationList';

export function RoundEntry({ round, table }: { round: Round; table: TableDetail }) {
  return (
    <article className="round" aria-labelledby={`round-${round.number}`}>
      <h3 id={`round-${round.number}`} className="round__number">
        라운드 {round.number}
      </h3>
      <p className="prose scene">{round.scene}</p>
      <DeclarationList round={round} table={table} />
    </article>
  );
}
