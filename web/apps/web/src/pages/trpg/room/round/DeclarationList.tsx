// web/apps/web/src/pages/trpg/room/round/DeclarationList.tsx
// 한 라운드의 선언들과 그 결과, 죽음의 굴림, 새로 들어온 캐릭터.
// 선언을 받는 동안 남의 선언은 글과 행동이 가려져 온다(null). 그때는 "선언을 냈습니다"만 적는다.
// 판정한 선언은 Stitch 20번의 판정 결과 줄이다: 머리(캐릭터 이름, 행동, 오른쪽에 "판정 성공"·"판정 실패"), 선언 글,
// 눈·보정·합·목표의 한 줄, 판정이 바꾼 것(공격의 줄이 맨 앞)의 한 줄. 성공·실패에 따라 왼쪽 띠의 색이 다르다(outcomeTone).
// 판정하지 않은 결과(사기, 건네기, 행동하지 못함 등)는 결과 한 줄이다(outcomeLine).

import type { Declaration, Round, TableDetail } from '../../../../api/types';
import { actionLabel, checkOutcome, deathSaveLine, outcomeLine, outcomeTone } from './roundView';

export function DeclarationList({ round, table }: { round: Round; table: TableDetail }) {
  if (round.declarations.length === 0 && round.death_saves.length === 0 && round.arrivals.length === 0) return null;
  return (
    <ul className="declarations">
      {round.declarations.map((declaration) => (
        <DeclarationItem key={declaration.user_id} declaration={declaration} table={table} />
      ))}
      {round.death_saves.map((save) => (
        <li key={`death-${save.user_id}`} className="declaration declaration--system">
          {deathSaveLine(save, table.rules.roll.style)}
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

function DeclarationItem({ declaration, table }: { declaration: Declaration; table: TableDetail }) {
  const check = checkOutcome(declaration.outcome, table.rules);
  const line = check ? null : outcomeLine(declaration.outcome, table.rules, table.currency ?? null);
  const tone = outcomeTone(declaration.outcome);
  return (
    <li className={tone ? `declaration declaration--${tone}` : 'declaration'}>
      <div className="declaration__head">
        <span className="declaration__name">{declaration.character_name}</span>
        {declaration.action ? <span className="hint">{actionLabel(declaration.action, table)}</span> : null}
        {check ? <span className="declaration__verdict">{check.success ? '판정 성공' : '판정 실패'}</span> : null}
      </div>
      {declaration.content !== null ? <span className="prose">{declaration.content}</span> : <span className="hint">선언을 냈습니다.</span>}
      {check ? <span className="declaration__outcome">{check.dice}</span> : null}
      {check && check.effects.length > 0 ? <span className="declaration__effect">{check.effects.join(' · ')}</span> : null}
      {line ? <span className="declaration__outcome">{line}</span> : null}
    </li>
  );
}
