// web/apps/web/src/pages/trpg/studio/scenarios/SheetFields.tsx
// 시트 하나의 칸(B9): 룰북의 능력치마다 점수, 그리고 최대 HP. 기본 시트와 프리젠의 창이 함께 쓴다.
// 검사와 보내기는 쓰는 쪽이 한다(sheetForm.ts). 모두 비우면 시트 없음이라고 적는다.

import { TextField } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';
import type { SheetDraft } from './sheetForm';

type Props = {
  legend: string;
  rules: Ruleset;
  draft: SheetDraft;
  hints: Record<string, string>;
  onChange: (draft: SheetDraft) => void;
};

export function SheetFields({ legend, rules, draft, hints, onChange }: Props) {
  return (
    <fieldset className="scenario-sheet">
      <legend>{legend}</legend>
      <p className="ui-field__hint">
        점수는 {rules.score_min}~{rules.score_max} 사이입니다. 모두 비우면 시트가 없는 것으로 저장하고, 게시 점검이 알려 줍니다.
      </p>
      <div className="ability-grid">
        {rules.abilities.map((ability) => (
          <TextField
            key={ability.key}
            label={ability.name}
            inputMode="numeric"
            value={draft.abilities[ability.key] ?? ''}
            onChange={(event) => onChange({ ...draft, abilities: { ...draft.abilities, [ability.key]: event.target.value } })}
            error={hints[ability.key]}
          />
        ))}
        <TextField
          label="최대 HP"
          inputMode="numeric"
          value={draft.maxHp}
          onChange={(event) => onChange({ ...draft, maxHp: event.target.value })}
          error={hints.max_hp}
        />
      </div>
    </fieldset>
  );
}
