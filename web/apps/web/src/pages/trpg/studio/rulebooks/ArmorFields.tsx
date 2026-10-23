// web/apps/web/src/pages/trpg/studio/rulebooks/ArmorFields.tsx
// 방어 규칙(#276) 고르기. 방식 넷 중 하나, 세이브면 목표값, 막는 방식이면 관통의 기준값.
// 주사위의 면 수(die)는 템플릿의 규칙에서 와서 목표값의 설명에 쓴다.
// 숫자 칸이 비어 있으면 오류 글 대신 설명만 둔다(아직 적지 않았다). 그동안 저장 단추는 꺼져 있다.

import { Radio, TextField } from '@ai-trpg/ui';
import type { ArmorChoice, ArmorDraft } from './rulebookForm';
import { ARMOR_CHOICES, armorText } from './rulebookView';

type Props = {
  draft: ArmorDraft;
  die: number | null;
  hints: Record<string, string>;
  onChange: (changes: Partial<ArmorDraft>) => void;
};

export function ArmorFields({ draft, die, hints, onChange }: Props) {
  const dieName = die ? `d${die}` : '판정의 주사위';
  return (
    <fieldset className="choice-list">
      <legend>방어 규칙</legend>
      {ARMOR_CHOICES.map((choice: ArmorChoice) => (
        <Radio
          key={choice}
          name="armor_mode"
          label={armorText(choice).label}
          description={armorText(choice).description}
          checked={draft.armor === choice}
          onChange={() => onChange({ armor: choice })}
        />
      ))}
      {draft.armor === 'save' ? (
        <div className="armor-number">
          <TextField
            label="세이브의 목표값"
            name="save_target"
            inputMode="numeric"
            value={draft.saveTarget}
            onChange={(event) => onChange({ saveTarget: event.target.value })}
            error={draft.saveTarget === '' ? undefined : hints.save_target}
          />
          <p className="ui-field__hint">{dieName}의 눈 + 막는 값(아머, 불굴 가운데 큰 것)이 이 값 이상이면 막습니다.</p>
        </div>
      ) : null}
      {draft.armor !== 'none' ? (
        <div className="armor-number">
          <TextField
            label="관통의 기준값"
            name="pierce_base"
            inputMode="numeric"
            value={draft.pierceBase}
            onChange={(event) => onChange({ pierceBase: event.target.value })}
            error={draft.pierceBase === '' ? undefined : hints.pierce_base}
          />
          <p className="ui-field__hint">관통력이 있는 무기는 눈 + 관통력이 맞은 부위의 방어 + 이 값 이상이면 방어구를 뚫습니다. 기본은 10입니다.</p>
        </div>
      ) : null}
    </fieldset>
  );
}
