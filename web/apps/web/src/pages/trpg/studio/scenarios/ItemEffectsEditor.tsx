// web/apps/web/src/pages/trpg/studio/scenarios/ItemEffectsEditor.tsx
// 소모품의 칸(B9 물건 규칙 창): 쓰면 나는 효과 목록(#800), 던지는 판정과 치료 보정(#277).
// 효과는 적힌 차례대로 낸다. 회복·피해는 룰북의 양의 등급, 풀기·부상은 룰북의 부상에서 고른다. 검사는 itemEffectsForm.ts.

import { Button, Checkbox, SelectField, TextField } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';
import { CheckSelects } from './CheckSelects';
import {
  curableInjuries,
  EFFECT_KINDS,
  EFFECT_LABELS,
  MAX_EFFECTS,
  newEffectDraft,
  toggleCure,
  type EffectDraft,
  type EffectKind,
  type ThrowDraft,
} from './itemEffectsForm';
import type { ItemRuleDraft } from './itemRuleForm';

type Props = {
  draft: ItemRuleDraft;
  rules: Ruleset | null;
  hints: Record<string, string>;
  update: (changes: Partial<ItemRuleDraft>) => void;
};

/** 소모품만의 칸들. 효과 목록, 던지기, 치료 보정이다 */
export function ConsumableFields({ draft, rules, hints, update }: Props) {
  return (
    <>
      <ItemEffectsEditor effects={draft.effects} rules={rules} hints={hints} onChange={(effects) => update({ effects })} />
      <ThrowFields thrown={draft.throw} rules={rules} error={hints.throw} onChange={(thrown) => update({ throw: thrown })} />
      <TextField
        label="치료에 붙여 쓸 때의 보정(선택, 1~10)"
        inputMode="numeric"
        value={draft.treatBonus}
        onChange={(event) => update({ treatBonus: event.target.value })}
        error={hints.treat_bonus}
      />
      <p className="ui-field__hint">붕대, 의료 키트. 치료 판정에 더하고, 쓰면 성공하든 실패하든 하나 없어집니다.</p>
    </>
  );
}

type EffectsProps = { effects: EffectDraft[]; rules: Ruleset | null; hints: Record<string, string>; onChange: (effects: EffectDraft[]) => void };

function ItemEffectsEditor({ effects, rules, hints, onChange }: EffectsProps) {
  const replace = (index: number, next: EffectDraft) => onChange(effects.map((one, at) => (at === index ? next : one)));
  return (
    <fieldset className="scenario-choices">
      <legend>쓰면 나는 효과(적힌 차례대로)</legend>
      <p className="ui-field__hint">
        비우면 써도 아무 일이 없습니다(연막탄처럼 서술만). 피해나 부상이 있는 물건은 동료에게 쓰지 못하고, 인물과 몬스터에게는 맞히는 판정을 거칩니다.
      </p>
      {effects.map((effect, index) => (
        <EffectRow
          key={index}
          index={index}
          effect={effect}
          rules={rules}
          error={hints[`effect.${index}`]}
          onChange={(next) => replace(index, next)}
          onRemove={() => onChange(effects.filter((_, at) => at !== index))}
        />
      ))}
      {hints.effects ? <p className="ui-field__error">{hints.effects}</p> : null}
      <Button variant="quiet" disabled={effects.length >= MAX_EFFECTS} onClick={() => onChange([...effects, newEffectDraft()])}>
        효과 더하기
      </Button>
    </fieldset>
  );
}

type RowProps = {
  index: number;
  effect: EffectDraft;
  rules: Ruleset | null;
  error: string | undefined;
  onChange: (effect: EffectDraft) => void;
  onRemove: () => void;
};

function EffectRow({ index, effect, rules, error, onChange, onRemove }: RowProps) {
  return (
    <fieldset className="scenario-choices" aria-label={`효과 ${index + 1}`}>
      <legend>효과 {index + 1}</legend>
      <SelectField label="종류" value={effect.kind} onChange={(event) => onChange(newEffectDraft(event.target.value as EffectKind))}>
        {EFFECT_KINDS.map((kind) => (
          <option key={kind} value={kind}>
            {EFFECT_LABELS[kind]}
          </option>
        ))}
      </SelectField>
      <EffectTarget effect={effect} rules={rules} onChange={onChange} />
      {error ? <p className="ui-field__error">{error}</p> : null}
      <Button variant="quiet" onClick={onRemove}>
        효과 {index + 1} 지우기
      </Button>
    </fieldset>
  );
}

type TargetProps = { effect: EffectDraft; rules: Ruleset | null; onChange: (effect: EffectDraft) => void };

/** 종류마다 고르는 것. 양, 풀 부상들, 입힐 부상 */
function EffectTarget({ effect, rules, onChange }: TargetProps) {
  if (!rules) return <p className="hint">룰북을 고르면 양과 부상을 고를 수 있습니다.</p>;
  if (effect.kind === 'heal' || effect.kind === 'damage') {
    return (
      <SelectField label="양" value={effect.magnitude} onChange={(event) => onChange({ ...effect, magnitude: event.target.value })}>
        <option value="">고르기</option>
        {rules.magnitudes.map((one) => (
          <option key={one.key} value={one.key}>
            {one.name}({one.count}d{one.sides})
          </option>
        ))}
      </SelectField>
    );
  }
  if (effect.kind === 'cure') {
    return (
      <div>
        {curableInjuries(rules).map((injury) => (
          <Checkbox
            key={injury.key}
            label={`${injury.name} 풀기`}
            checked={effect.injuries.includes(injury.key)}
            onChange={() => onChange({ ...effect, injuries: toggleCure(effect.injuries, injury.key, rules) })}
          />
        ))}
      </div>
    );
  }
  return (
    <SelectField label="입힐 부상" value={effect.injury} onChange={(event) => onChange({ ...effect, injury: event.target.value })}>
      <option value="">고르기</option>
      {rules.injuries.map((one) => (
        <option key={one.key} value={one.key}>
          {one.name}
        </option>
      ))}
    </SelectField>
  );
}

type ThrowProps = { thrown: ThrowDraft; rules: Ruleset | null; error: string | undefined; onChange: (thrown: ThrowDraft) => void };

/** 던지는 판정(#277). 켜면 행동 '던지기'로 같은 장소의 몬스터나 인물에게 던진다 */
function ThrowFields({ thrown, rules, error, onChange }: ThrowProps) {
  return (
    <fieldset className="scenario-choices">
      <legend>던지기</legend>
      <Checkbox label="던질 수 있다" checked={thrown.on} onChange={(event) => onChange({ ...thrown, on: event.target.checked })} />
      {thrown.on ? (
        <>
          <CheckSelects
            label="던지는 판정"
            rules={rules}
            ability={thrown.ability}
            difficulty={thrown.difficulty}
            error={error}
            onChange={(changes) => onChange({ ...thrown, ...changes })}
          />
          {rules ? (
            <SelectField label="맞으면 다치는 양" value={thrown.harm} onChange={(event) => onChange({ ...thrown, harm: event.target.value })}>
              <option value="">고르기</option>
              {rules.magnitudes.map((one) => (
                <option key={one.key} value={one.key}>
                  {one.name}({one.count}d{one.sides})
                </option>
              ))}
            </SelectField>
          ) : null}
        </>
      ) : null}
    </fieldset>
  );
}
