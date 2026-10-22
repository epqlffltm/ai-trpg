// web/apps/web/src/pages/trpg/room/character/PointBuyInputs.tsx
// 점수로 능력치 사기(point_buy). 능력치마다 값표의 점수 중 하나를 고르고, 쓴 값과 남은 값을 바로 보인다.
// 총점을 다 쓰지 않아도 된다. 넘으면 보내기를 막는다(맞는지는 서버가 다시 본다).

import { SelectField } from '@ai-trpg/ui';
import type { Ruleset } from '../../../../api/types';
import { costOf, pointsSpent, purchasableScores } from './characterForm';

type Props = {
  rules: Ruleset;
  scores: Record<string, number>;
  onChange: (scores: Record<string, number>) => void;
};

export function PointBuyInputs({ rules, scores, onChange }: Props) {
  const pointBuy = rules.point_buy;
  if (!pointBuy) return <p className="hint">이 규칙에는 점수제가 없습니다.</p>;
  const spent = pointsSpent(pointBuy, scores);
  return (
    <>
      <p className="points" aria-live="polite">
        쓴 값 <strong>{spent ?? '?'}</strong> / 총점 {pointBuy.budget}
        {spent !== null ? ` · 남은 값 ${pointBuy.budget - spent}` : ''}
      </p>
      <div className="ability-grid">
        {rules.abilities.map((ability) => (
          <SelectField
            key={ability.key}
            label={ability.name}
            value={String(scores[ability.key] ?? '')}
            onChange={(event) => onChange({ ...scores, [ability.key]: Number(event.target.value) })}
          >
            {purchasableScores(pointBuy).map((score) => (
              <option key={score} value={score}>
                {score} (값 {costOf(pointBuy, score)})
              </option>
            ))}
          </SelectField>
        ))}
      </div>
    </>
  );
}
