// web/apps/web/src/pages/trpg/room/character/SheetStats.tsx
// 캐릭터의 숫자 한 줄. 최대 HP 와 능력치의 점수. 능력치의 열쇠(str …)는 테이블의 규칙의 이름(근력 …)으로 읽는다.
// 최대 HP 를 서버가 시작할 때 구하는 것이면 "어림"이라고 적는다.

import type { Ruleset } from '../../../../api/types';
import { abilityRows } from '../../scenario/PregenList';

type Props = {
  rules: Ruleset;
  abilities: Record<string, number> | null;
  maxHp: number | null;
  /** 최대 HP 가 화면의 어림인가 */
  estimated?: boolean;
};

export function SheetStats({ rules, abilities, maxHp, estimated = false }: Props) {
  return (
    <dl className="pregen__stats">
      {maxHp !== null ? (
        <div className="pregen__stat">
          <dt>{estimated ? '최대 HP(어림)' : '최대 HP'}</dt>
          <dd>{maxHp}</dd>
        </div>
      ) : null}
      {abilityRows(abilities ?? {}, [...rules.abilities]).map(([name, score]) => (
        <div key={name} className="pregen__stat">
          <dt>{name}</dt>
          <dd>{score}</dd>
        </div>
      ))}
    </dl>
  );
}
