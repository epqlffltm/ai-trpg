// web/apps/web/src/pages/trpg/room/status/HpBar.tsx
// HP 한 줄. "HP 7 / 12" 와 막대. 쓰러졌으면 죽음의 굴림의 수를, 죽었으면 그렇다고 적는다.
// 막대는 꾸밈이다. 읽는 값은 글(그리고 meter 의 값)에 있다.

import type { Ruleset, Sheet } from '../../../../api/types';
import { conditionOf, deathSaveProgress, hpRatio } from './statusView';

export function HpBar({ sheet, rules }: { sheet: Sheet; rules: Ruleset }) {
  const condition = conditionOf(sheet);
  return (
    <div className={`hp hp--${condition}`}>
      <span className="hp__text">
        HP {Math.max(0, sheet.hp)} / {sheet.max_hp}
      </span>
      <meter className="hp__meter" min={0} max={sheet.max_hp} value={Math.max(0, sheet.hp)} aria-hidden="true">
        {Math.round(hpRatio(sheet) * 100)}%
      </meter>
      {condition === 'downed' ? <span className="hp__state">쓰러짐 · {deathSaveProgress(sheet, rules)}</span> : null}
      {condition === 'dead' ? <span className="hp__state">죽었습니다</span> : null}
    </div>
  );
}
