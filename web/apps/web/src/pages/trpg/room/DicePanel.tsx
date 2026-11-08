// web/apps/web/src/pages/trpg/room/DicePanel.tsx
// 대화창의 주사위 탭(#404). 자유 굴림을 한다. 빠른 단추(d4~d100)와 직접 적는 칸("2d6+1"), 최근 굴림 몇 개.
// 눈은 서버가 굴린다. 굴린 것은 이벤트(dice_rolled)로 모두에게 가고, 최근 굴림은 그 이벤트에서 읽는다.
// 게임의 상태와 무관하다. 판정도 피해도 아니고 서술하는 AI 도 받지 않는다. 끝난 테이블에서는 굴리지 못한다.

import { Button } from '@ai-trpg/ui';
import type { UseQueryResult } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { postFreeRoll } from '../../../api/tableRoom';
import type { EventPage, FreeRoll, TableDetail } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { useCountdown } from '../../../hooks/useCountdown';
import { DICE_MAX_LENGTH, DICE_SHORTCUTS, readableDice, recentRolls } from './diceForm';
import { describeDiceProblem } from './roomProblem';

type Props = {
  table: TableDetail;
  events: UseQueryResult<EventPage>;
  myId: string | undefined;
  nameOfMember: (userId: string) => string;
};

export function DicePanel({ table, events, myId, nameOfMember }: Props) {
  const rolls = recentRolls(events.data?.items ?? [], myId, nameOfMember);
  return (
    <section className="room-panel chat" aria-labelledby="dice-heading">
      <h2 id="dice-heading">주사위</h2>
      <p className="hint">게임과 무관한 굴림입니다. 판정이나 피해가 되지 않고, 굴린 것은 모두에게 보입니다.</p>
      {table.status === 'ended' ? <p className="hint">끝난 테이블에서는 굴릴 수 없습니다.</p> : <DiceForm tableId={table.id} />}
      {rolls.length === 0 ? (
        <p className="hint">아직 굴린 주사위가 없습니다.</p>
      ) : (
        <ol className="chat__messages" aria-label="최근 굴림" aria-live="polite">
          {rolls.map((roll) => (
            <li key={roll.sequence} className={roll.mine ? 'chat__message whisper--sent' : 'chat__message'}>
              <span className="chat__name">{roll.who}</span>
              <span className="prose">{roll.text}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function DiceForm({ tableId }: { tableId: string }) {
  const [dice, setDice] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();
  const ready = !busy && wait.remaining === 0;

  async function roll(text: string): Promise<FreeRoll | null> {
    setBusy(true);
    setProblem(undefined);
    try {
      return await postFreeRoll(tableId, text.trim());
    } catch (error) {
      const next = describeDiceProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || !readableDice(dice)) return;
    if (await roll(dice)) setDice('');
  }

  const typed = dice.trim() !== '';
  return (
    <form className="chat__form dice__form" onSubmit={submit} noValidate aria-label="주사위 굴리기">
      <ProblemNotice problem={problem} />
      <div className="dice__shortcuts" role="group" aria-label="빠른 굴림">
        {DICE_SHORTCUTS.map((shortcut) => (
          <Button key={shortcut} variant="secondary" disabled={!ready} onClick={() => void roll(shortcut)}>
            {shortcut}
          </Button>
        ))}
      </div>
      <label className="visually-hidden" htmlFor="dice-input">
        주사위 설명
      </label>
      <input
        id="dice-input"
        className="ui-field__input"
        maxLength={DICE_MAX_LENGTH}
        value={dice}
        placeholder="예: 2d6+1"
        aria-invalid={typed && !readableDice(dice) ? true : undefined}
        aria-describedby="dice-hint"
        onChange={(event) => setDice(event.target.value)}
      />
      <Button type="submit" busy={busy} disabled={!ready || !readableDice(dice)}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에` : '굴리기'}
      </Button>
      <p id="dice-hint" className="ui-field__hint">
        면 수는 4, 6, 8, 10, 12, 20, 100. 10개까지, 보정은 ±100까지입니다.
      </p>
    </form>
  );
}
