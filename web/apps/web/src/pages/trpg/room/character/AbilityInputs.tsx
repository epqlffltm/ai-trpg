// web/apps/web/src/pages/trpg/room/character/AbilityInputs.tsx
// 능력치를 직접 적기(manual). 규칙의 능력치마다 숫자 칸 하나. 범위(score_min~score_max) 안이면 무엇이든 된다.
// 비운 칸은 NaN 으로 둔다. 보내기 전에 막는다(characterForm.ts 의 draftHints).

import { TextField } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';

type Props = {
  rules: Ruleset;
  scores: Record<string, number>;
  onChange: (scores: Record<string, number>) => void;
};

export function AbilityInputs({ rules, scores, onChange }: Props) {
  return (
    <div className="ability-grid">
      {rules.abilities.map((ability) => (
        <TextField
          key={ability.key}
          label={ability.name}
          type="number"
          inputMode="numeric"
          min={rules.score_min}
          max={rules.score_max}
          step={1}
          value={Number.isNaN(scores[ability.key]) ? '' : String(scores[ability.key] ?? '')}
          onChange={(event) => onChange({ ...scores, [ability.key]: toScore(event.target.value) })}
        />
      ))}
    </div>
  );
}

/** 칸의 글을 점수로. 비우면 NaN */
function toScore(text: string): number {
  return text.trim() === '' ? Number.NaN : Number(text);
}
