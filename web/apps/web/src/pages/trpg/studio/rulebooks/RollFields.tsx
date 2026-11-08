// web/apps/web/src/pages/trpg/studio/rulebooks/RollFields.tsx
// 룰북의 판정 방식(#404) 고르기. 주사위의 면 수와 개수, 성공을 가르는 쪽, under 면 난이도마다 기량에 더하는 값.
// 검사는 rollForm.ts. 숫자 칸이 비어 있으면 오류 글 대신 설명만 둔다(아직 적지 않았다). 그동안 저장 단추는 꺼져 있다.

import { Radio, TextField } from '@ai-trpg/ui';
import { diceName, ROLL_STYLES, type RollDraft, type ShiftDraft } from './rollForm';
import { rollStyleText } from './rulebookView';

type Props = {
  draft: RollDraft;
  hints: Record<string, string>;
  onChange: (draft: RollDraft) => void;
};

export function RollFields({ draft, hints, onChange }: Props) {
  const update = (changes: Partial<RollDraft>) => onChange({ ...draft, ...changes });
  const replace = (index: number, next: ShiftDraft) => update({ shifts: draft.shifts.map((one, at) => (at === index ? next : one)) });
  const dice = diceName(draft);
  return (
    <fieldset className="choice-list">
      <legend>판정 방식</legend>
      <div className="armor-number">
        <TextField
          label="주사위의 면 수"
          name="die"
          inputMode="numeric"
          value={draft.die}
          onChange={(event) => update({ die: event.target.value })}
          error={draft.die === '' ? undefined : hints.die}
        />
        <TextField
          label="굴리는 개수"
          name="roll_count"
          inputMode="numeric"
          value={draft.count}
          onChange={(event) => update({ count: event.target.value })}
          error={draft.count === '' ? undefined : hints.roll_count}
        />
        <p className="ui-field__hint">
          {dice ? `${dice}를 굴려 더합니다. ` : ''}판정, 죽음의 굴림, 되살아나기, 관통과 세이브, 선공을 가르는 굴림이 모두 이 주사위입니다.
        </p>
      </div>
      {ROLL_STYLES.map((style) => (
        <Radio
          key={style}
          name="roll_style"
          label={rollStyleText(style).label}
          description={rollStyleText(style).description}
          checked={draft.style === style}
          onChange={() => update({ style })}
        />
      ))}
      {hints.roll_style ? (
        <p className="ui-field__error" role="alert">
          {hints.roll_style}
        </p>
      ) : null}
      {draft.style === 'under' ? (
        <div className="armor-number">
          <p className="ui-field__hint">난이도마다 기량에 더하는 값입니다. 어려울수록 빼는 값을 적습니다(예: 어려움 -20).</p>
          {draft.shifts.map((shift, index) => (
            <TextField
              key={shift.key}
              label={`${shift.name}에서 기량에 더하는 값`}
              name={`shift.${shift.key}`}
              inputMode="numeric"
              value={shift.value}
              onChange={(event) => replace(index, { ...shift, value: event.target.value })}
              error={shift.value === '' ? undefined : hints[`shift.${shift.key}`]}
            />
          ))}
        </div>
      ) : null}
    </fieldset>
  );
}
