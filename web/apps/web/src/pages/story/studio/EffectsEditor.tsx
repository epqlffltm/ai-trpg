// web/apps/web/src/pages/story/studio/EffectsEditor.tsx
// 효과 목록의 칸(D7). 효과마다 종류·대상·크기를 고른다. 이벤트가 열릴 때와 선택지를 고를 때가 함께 쓴다.
// 이름표 앞에 쓰는 쪽의 이름(prefix)을 붙여 같은 화면의 여러 목록을 가른다.

import { Button, SelectField, TextField } from '@ai-trpg/ui';
import type { ConditionChoices } from './conditionsForm';
import { addEffect, changeEffect, EFFECT_KIND_ORDER, EFFECT_KINDS, EFFECTS_MAX, effectTargets, removeEffect, type EffectDraft } from './effectsForm';
import { labelOr } from './worldLabels';

type Props = { prefix: string; effects: EffectDraft[]; choices: ConditionChoices; hints: Record<number, string>; onChange: (effects: EffectDraft[]) => void; emptyText: string };

export function EffectsEditor({ prefix, effects, choices, hints, onChange, emptyText }: Props) {
  return (
    <fieldset className="scenario-choices">
      <legend>{prefix}의 효과</legend>
      {effects.length === 0 ? <p className="hint">{emptyText}</p> : null}
      <ol className="plain-list" aria-label={`${prefix}의 효과`}>
        {effects.map((effect, index) => {
          const spec = EFFECT_KINDS[effect.kind];
          const label = `${prefix}의 효과 ${index + 1}`;
          return (
            <li key={index} className="scenario-opening">
              <SelectField label={`${label}의 종류`} value={effect.kind} onChange={(event) => onChange(changeEffect(effects, index, { kind: event.target.value as EffectDraft['kind'] }))}>
                {EFFECT_KIND_ORDER.map((kind) => (
                  <option key={kind} value={kind}>
                    {EFFECT_KINDS[kind].label}
                  </option>
                ))}
              </SelectField>
              <SelectField label={`${label}의 대상`} value={effect.target} onChange={(event) => onChange(changeEffect(effects, index, { target: event.target.value }))}>
                <option value="">고르지 않음</option>
                {effectTargets(effect.kind, choices).map((choice, at) => (
                  <option key={choice.id} value={choice.id}>
                    {labelOr(choice.name, `${at + 1}번째`)}
                  </option>
                ))}
              </SelectField>
              {spec.amount ? (
                <TextField
                  label={`${label}의 ${spec.amount === 'signed' ? '크기(-100~100)' : '수(1~99)'}`}
                  inputMode="numeric"
                  value={effect.amount}
                  onChange={(event) => onChange(changeEffect(effects, index, { amount: event.target.value }))}
                />
              ) : null}
              {hints[index] ? <p className="ui-field__error">{hints[index]}</p> : null}
              <div className="form-actions">
                <Button variant="quiet" aria-label={`${label} 지우기`} onClick={() => onChange(removeEffect(effects, index))}>
                  지우기
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      <p>
        <Button variant="secondary" disabled={effects.length >= EFFECTS_MAX} onClick={() => onChange(addEffect(effects))}>
          {prefix}의 효과 더하기
        </Button>
      </p>
    </fieldset>
  );
}
