// web/apps/web/src/pages/trpg/studio/scenarios/ItemAidsEditor.tsx
// 물건 규칙 창의 칸(B9): 이 물건이 거드는 행동들(#802, 거들기). 모든 종류의 물건에 있다.
// 줄마다 행동, 판정에 더하는 보정, 굴린 뒤 어떻게 되나를 고른다. 더하기·지우기. 검사는 itemAidsForm.ts.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import { AID_ACT_LABELS, AID_ACTS, AID_WEAR_LABELS, AID_WEARS, newAidDraft, type AidAct, type AidDraft, type AidWear } from './itemAidsForm';

type Props = { aids: AidDraft[]; hints: Record<string, string>; onChange: (aids: AidDraft[]) => void };

export function ItemAidsEditor({ aids, hints, onChange }: Props) {
  const replace = (index: number, next: AidDraft) => onChange(aids.map((one, at) => (at === index ? next : one)));
  const added = newAidDraft(aids);
  return (
    <fieldset className="scenario-choices">
      <legend>거드는 행동</legend>
      <p className="ui-field__hint">
        치료, 따기, 고치기, 부수기, 넘기에 붙여 쓰면 판정에 보정을 더합니다(의료 키트, 락픽, 공구, 쇠지렛대, 밧줄). 도구가 있어야 하는 문은 그
        행동을 거드는 물건을 붙여야 다룹니다.
      </p>
      {aids.map((aid, index) => (
        <AidRow
          key={aid.act}
          aid={aid}
          taken={aids.map((one) => one.act)}
          error={hints[`aid.${index}`]}
          onChange={(next) => replace(index, next)}
          onRemove={() => onChange(aids.filter((_, at) => at !== index))}
        />
      ))}
      {hints.aids ? <p className="ui-field__error">{hints.aids}</p> : null}
      <Button variant="quiet" disabled={added === null} onClick={() => added && onChange([...aids, added])}>
        거드는 행동 더하기
      </Button>
    </fieldset>
  );
}

type RowProps = {
  aid: AidDraft;
  taken: AidAct[];
  error: string | undefined;
  onChange: (aid: AidDraft) => void;
  onRemove: () => void;
};

/** 거들기 한 줄. 다른 줄에 적은 행동은 고를 수 없다 */
function AidRow({ aid, taken, error, onChange, onRemove }: RowProps) {
  const label = AID_ACT_LABELS[aid.act];
  return (
    <fieldset className="scenario-choices" aria-label={`${label} 거들기`}>
      <legend>{label}</legend>
      <SelectField label="행동" value={aid.act} onChange={(event) => onChange({ ...aid, act: event.target.value as AidAct })}>
        {AID_ACTS.filter((act) => act === aid.act || !taken.includes(act)).map((act) => (
          <option key={act} value={act}>
            {AID_ACT_LABELS[act]}
          </option>
        ))}
      </SelectField>
      <TextField label="보정(0~10, 비우면 0)" inputMode="numeric" value={aid.bonus} onChange={(event) => onChange({ ...aid, bonus: event.target.value })} error={error} />
      <SelectField label="굴린 뒤" value={aid.wear} onChange={(event) => onChange({ ...aid, wear: event.target.value as AidWear })}>
        {AID_WEARS.map((wear) => (
          <option key={wear} value={wear}>
            {AID_WEAR_LABELS[wear]}
          </option>
        ))}
      </SelectField>
      <Button variant="quiet" onClick={onRemove}>
        {label} 거들기 지우기
      </Button>
    </fieldset>
  );
}
