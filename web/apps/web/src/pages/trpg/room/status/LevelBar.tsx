// web/apps/web/src/pages/trpg/room/status/LevelBar.tsx
// 성장(#286) 한 줄. "레벨 3 · 경험치 450 / 900" 과 다음 레벨까지의 막대, 쌓인 점수. HP 줄(HpBar.tsx)과 같은 모양이다.
// 성장이 없는 규칙이면 그리지 않는다. 막대는 꾸밈이다. 읽는 값은 글에 있다. 레벨을 올리는 것은 엔진뿐이다.

import type { Ruleset, Sheet } from '../../../../api/types';
import { levelLine, levelRatio } from './growthView';

export function LevelBar({ sheet, rules }: { sheet: Sheet; rules: Ruleset }) {
  const line = levelLine(sheet, rules);
  if (line === null) return null;
  return (
    <div className="hp">
      <span className="hp__text">{line}</span>
      <meter className="hp__meter" min={0} max={1} value={levelRatio(sheet, rules)} aria-hidden="true" />
      {sheet.points > 0 ? <span className="hp__state">놓지 않은 능력치 점수 {sheet.points}</span> : null}
    </div>
  );
}
