// web/apps/web/src/pages/trpg/room/FriendlyFirePanel.tsx
// 동료 피해(#803). 앉은 사람 모두에게 보인다. 접어 둔다.
//   - 테이블의 정도(방장이 정한다. 방장의 운영에서 바꾼다)
//   - 나를 겨누는 것을 받아들이는 정도. 내가 고른다. 고르면 바로 보낸다. 끔이 기본이다
//   - 다른 사람마다 지금 해칠 수 있는 정도(테이블의 것과 그 사람이 받아들인 것 중 낮은 것)
// 자기 자신에게 하는 것은 늘 된다. 맞는지는 서버가 받을 때와 라운드를 닫을 때 다시 본다.

import { SelectField } from '@ai-trpg/ui';
import { changeFriendlyFireConsent } from '../../../api/tableRoom';
import type { FriendlyFire, TableDetail } from '../../../api/types';
import { ProblemNotice } from '../../../components/ProblemNotice';
import { FRIENDLY_FIRE_VALUES, friendlyFireLabel, lowerFriendlyFire } from '../labels';
import { useHostAction } from './host/useHostAction';

type Props = { table: TableDetail; myId: string | undefined; nameOfMember: (userId: string) => string };

export function FriendlyFirePanel({ table, myId, nameOfMember }: Props) {
  // 바뀐 테이블을 받아 화면의 것을 바꾸는 일은 방장의 운영과 같다(useHostAction 은 방장만의 것이 아니다)
  const action = useHostAction(table.id);
  const mine = table.members.find((member) => member.user_id === myId);
  if (table.status === 'ended' || mine === undefined) return null;
  const others = table.members.filter((member) => member.user_id !== myId);
  return (
    <details className="room-panel">
      <summary>
        <h2 className="host-panel__title">동료 피해</h2>
      </summary>
      <p className="hint">
        테이블: {friendlyFireLabel(table.friendly_fire)}. 각자 받아들인 정도와 견주어 낮은 쪽이 듭니다. 장난은 HP 1 아래로 내리지
        않고 짧은 부상만 입힙니다.
      </p>
      <ProblemNotice problem={action.problem} />
      <SelectField
        label="나를 겨누는 것 받아들이기"
        value={mine.friendly_fire}
        disabled={action.busy}
        onChange={(event) =>
          void action.run(() => changeFriendlyFireConsent(table.id, event.target.value as FriendlyFire))
        }
      >
        {FRIENDLY_FIRE_VALUES.map((level) => (
          <option key={level} value={level}>
            {friendlyFireLabel(level)}
          </option>
        ))}
      </SelectField>
      {others.length > 0 ? (
        <ul className="plain-list" aria-label="동료마다 지금 드는 정도">
          {others.map((member) => (
            <li key={member.user_id}>
              {nameOfMember(member.user_id)}: {friendlyFireLabel(lowerFriendlyFire(table.friendly_fire, member.friendly_fire))}
            </li>
          ))}
        </ul>
      ) : null}
    </details>
  );
}
