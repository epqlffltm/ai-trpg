// web/apps/web/src/pages/trpg/room/status/RaiseButton.tsx
// 내 캐릭터의 쌓인 점수를 능력치에 놓는 단추와 창(#286). 점수가 있을 때만 단추를 둔다.
// 창에서 능력치마다 올리고 내려 고른 뒤 한 번에 보낸다. 남은 점수와 규칙의 상한을 넘게는 고르지 못한다.
// 놓은 점수는 되돌리지 못한다고 알린다. 최대 HP 는 서버가 다시 정한다(보정이 오르면 오른다).

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { Ruleset, Sheet } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { canStepUp, raisesLine, spent, stepped, type Raises } from './growthView';
import type { Raising } from './useRaise';

type Props = { sheet: Sheet; rules: Ruleset; raising: Raising };

export function RaiseButton({ sheet, rules, raising }: Props) {
  const [open, setOpen] = useState(false);
  const [raises, setRaises] = useState<Raises>({});
  const close = useCallback(() => setOpen(false), []);
  if (sheet.points <= 0) return null;

  function start() {
    setRaises({});
    raising.reset();
    setOpen(true);
  }

  async function confirm() {
    if (await raising.raise(raises)) setOpen(false);
  }

  const left = sheet.points - spent(raises);
  return (
    <>
      <button type="button" className="action-chip" disabled={!raising.enabled || raising.busy} onClick={start}>
        능력치 올리기 ({sheet.points})
      </button>
      <Dialog title="능력치 올리기" open={open} onClose={close}>
        <p>
          남은 점수 {left} / {sheet.points}. 한 점이 능력치 1 입니다. 놓은 점수는 되돌릴 수 없습니다.
        </p>
        <ul className="plain-list" aria-label="능력치">
          {rules.abilities.map((ability) => {
            const score = (sheet.abilities[ability.key] ?? 0) + (raises[ability.key] ?? 0);
            return (
              <li key={ability.key} className="ability-grid">
                <span>
                  {ability.name} {score}
                </span>
                <button
                  type="button"
                  className="action-chip"
                  aria-label={`${ability.name} 내리기`}
                  disabled={(raises[ability.key] ?? 0) === 0}
                  onClick={() => setRaises((current) => stepped(current, ability.key, -1, sheet, rules))}
                >
                  −
                </button>
                <button
                  type="button"
                  className="action-chip"
                  aria-label={`${ability.name} 올리기`}
                  disabled={!canStepUp(raises, ability.key, sheet, rules)}
                  onClick={() => setRaises((current) => stepped(current, ability.key, 1, sheet, rules))}
                >
                  +
                </button>
              </li>
            );
          })}
        </ul>
        {spent(raises) > 0 ? <p className="hint">{raisesLine(raises, sheet, rules)}</p> : null}
        <ProblemNotice problem={raising.problem} />
        <div className="actions">
          <Button busy={raising.busy} disabled={spent(raises) === 0 || !raising.enabled} onClick={() => void confirm()}>
            올리기
          </Button>
        </div>
      </Dialog>
    </>
  );
}
