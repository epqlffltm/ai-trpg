// web/apps/web/src/pages/trpg/scenario/PregenList.tsx
// 프리젠(제작자가 만든 캐릭터)의 이름, 설명, 숫자. 숫자의 열쇠(str …)는 시나리오의 능력치 이름(근력 …)으로 읽는다.
// 함께 받는 소지품은 서버가 싣지 않는다. 제작자가 붙인 캐릭터 그림(#983)이 있으면 이름 앞에 보인다.

import type { ListingPregen, PublicListingDetail } from '../../../api/types';
import { ListingAvatar } from '../portraits/CharacterAvatar';

type Ability = PublicListingDetail['abilities'][number];

type Props = { scenarioId: string; pregens: ListingPregen[]; abilities: Ability[] };

export function PregenList({ scenarioId, pregens, abilities }: Props) {
  return (
    <ul className="pregens">
      {pregens.map((pregen) => (
        <li key={pregen.name} className="pregen">
          <div className="pregen__head">
            {pregen.portrait_id ? <ListingAvatar scenarioId={scenarioId} portraitId={pregen.portrait_id} name={pregen.name} /> : null}
            <p className="pregen__name">{pregen.name}</p>
          </div>
          {pregen.description ? <p className="pregen__description">{pregen.description}</p> : null}
          <dl className="pregen__stats">
            <div className="pregen__stat">
              <dt>최대 HP</dt>
              <dd>{pregen.sheet.max_hp}</dd>
            </div>
            {abilityRows(pregen.sheet.abilities, abilities).map(([name, score]) => (
              <div key={name} className="pregen__stat">
                <dt>{name}</dt>
                <dd>{score}</dd>
              </div>
            ))}
          </dl>
        </li>
      ))}
    </ul>
  );
}

/** [이름, 점수]. 시나리오의 능력치 차례대로, 이름이 없는 열쇠는 열쇠 그대로 뒤에 붙인다 */
export function abilityRows(scores: Record<string, number> | undefined, abilities: Ability[]): [string, number][] {
  const values = scores ?? {};
  const named = abilities.filter((ability) => ability.key in values).map((ability): [string, number] => [ability.name, values[ability.key] ?? 0]);
  const known = new Set(abilities.map((ability) => ability.key));
  const rest = Object.entries(values).filter(([key]) => !known.has(key));
  return [...named, ...rest];
}
