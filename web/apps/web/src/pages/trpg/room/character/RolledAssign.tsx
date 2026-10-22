// web/apps/web/src/pages/trpg/room/character/RolledAssign.tsx
// 주사위로 굴린 점수 놓기(rolled). 굴리는 것은 서버다(POST .../character/roll). 굴린 눈과 점수를 보이고,
// 점수를 능력치에 하나씩 놓게 한다. 다른 능력치가 쓴 점수는 고를 수 없다.
//
// 캐릭터 하나에 한 번 굴린다. 다시 굴리려면 방장이 "한 번 더"를 줘야 한다(reroll_granted).
// 굴리면 앞에서 주사위로 정한 캐릭터는 지워진다(서버). 굴린 것은 앉은 사람 모두에게 보인다.

import { Button, SelectField } from '@ai-trpg/ui';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { rollAbilities } from '../../../../api/tableRoom';
import type { AbilityRoll, TableDetail } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { tableQuery } from '../roomQueries';
import { currentSlots, slotTaken, type CharacterDraft } from './characterForm';
import { describeCharacterProblem, type CharacterProblem } from './characterProblem';

type Props = {
  table: TableDetail;
  roll: AbilityRoll | null;
  canRoll: boolean;
  draft: CharacterDraft;
  onPlace: (key: string, slot: number | null) => void;
};

export function RolledAssign({ table, roll, canRoll, draft, onPlace }: Props) {
  const slots = currentSlots(draft, roll);
  return (
    <>
      <RollButton table={table} roll={roll} canRoll={canRoll} />
      {roll ? (
        <>
          <RolledScores roll={roll} />
          <div className="ability-grid">
            {table.rules.abilities.map((ability) => (
              <SelectField
                key={ability.key}
                label={ability.name}
                value={slots[ability.key] === undefined ? '' : String(slots[ability.key])}
                onChange={(event) => onPlace(ability.key, event.target.value === '' ? null : Number(event.target.value))}
              >
                <option value="">고르기</option>
                {roll.scores.map((score, slot) => (
                  <option key={slot} value={slot} disabled={slotTaken(slots, slot, ability.key)}>
                    {slot + 1}번 · {score}
                  </option>
                ))}
              </SelectField>
            ))}
          </div>
        </>
      ) : null}
    </>
  );
}

/** 굴린 점수와 눈. "1번 15 (6, 5, 4, 1)". 번호는 놓을 때 고르는 이름과 같다 */
function RolledScores({ roll }: { roll: AbilityRoll }) {
  return (
    <ol className="rolled-scores" aria-label="굴린 점수">
      {roll.scores.map((score, slot) => (
        <li key={slot}>
          {slot + 1}번 <strong>{score}</strong> <span className="hint">({(roll.dice[slot] ?? []).join(', ')})</span>
        </li>
      ))}
    </ol>
  );
}

function RollButton({ table, roll, canRoll }: { table: TableDetail; roll: AbilityRoll | null; canRoll: boolean }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<CharacterProblem | undefined>();
  const how = table.rules.score_roll;

  async function rollNow() {
    setBusy(true);
    setProblem(undefined);
    try {
      queryClient.setQueryData(tableQuery(table.id).queryKey, await rollAbilities(table.id));
    } catch (error) {
      const next = describeCharacterProblem(error);
      setProblem(next);
      if (next.refresh) void queryClient.invalidateQueries({ queryKey: tableQuery(table.id).queryKey });
    }
    setBusy(false);
  }

  return (
    <div className="roll">
      <ProblemNotice problem={problem} />
      {how ? (
        <p className="hint">
          점수 하나마다 {how.sides}면체 {how.count}개를 굴려 높은 {how.keep}개를 더합니다. 캐릭터 하나에 한 번 굴립니다.
        </p>
      ) : null}
      {canRoll ? (
        <Button busy={busy} variant={roll ? 'secondary' : 'primary'} onClick={rollNow}>
          {roll ? '다시 굴리기' : '주사위 굴리기'}
        </Button>
      ) : (
        <p className="hint">{rerollHint(table)}</p>
      )}
    </div>
  );
}

function rerollHint(table: TableDetail): string {
  return table.reroll_allowed
    ? '다시 굴리려면 방장이 "한 번 더"를 줘야 합니다.'
    : '이 테이블에서는 다시 굴릴 수 없습니다.';
}
