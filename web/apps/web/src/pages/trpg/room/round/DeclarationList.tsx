// web/apps/web/src/pages/trpg/room/round/DeclarationList.tsx
// 한 라운드의 선언들과 그 결과, 죽음의 굴림, 새로 들어온 캐릭터.
// 선언을 받는 동안 남의 선언은 글과 행동이 가려져 온다(null). 그때는 "선언을 냈습니다"만 적는다.

import type { Round, TableDetail } from '../../../../api/types';
import { actionLabel, deathSaveLine, outcomeLine } from './roundView';

export function DeclarationList({ round, table }: { round: Round; table: TableDetail }) {
  if (round.declarations.length === 0 && round.death_saves.length === 0 && round.arrivals.length === 0) return null;
  return (
    <ul className="declarations">
      {round.declarations.map((declaration) => (
        <li key={declaration.user_id} className="declaration">
          <span className="declaration__name">{declaration.character_name}</span>
          {declaration.content !== null ? (
            <span className="prose">{declaration.content}</span>
          ) : (
            <span className="hint">선언을 냈습니다.</span>
          )}
          {declaration.action ? <span className="hint">{actionLabel(declaration.action, table)}</span> : null}
          {outcomeLine(declaration.outcome, table.rules) ? (
            <span className="declaration__outcome">{outcomeLine(declaration.outcome, table.rules)}</span>
          ) : null}
        </li>
      ))}
      {round.death_saves.map((save) => (
        <li key={`death-${save.user_id}`} className="declaration declaration--system">
          {deathSaveLine(save)}
        </li>
      ))}
      {round.arrivals.map((arrival) => (
        <li key={`arrival-${arrival.user_id}`} className="declaration declaration--system">
          {arrival.character_name}: 새로 들어왔습니다. 다음 라운드부터 선언합니다.
        </li>
      ))}
    </ul>
  );
}
