// web/apps/web/src/pages/trpg/room/status/CharacterCards.tsx
// 앉은 사람마다의 캐릭터(C). 이름, 사람, HP, 부상, 능력치, 떠난 캐릭터. 나를 맨 앞에 둔다.
// 앉은 사람은 서로의 시트를 본다(서버가 모두에게 준다).

import type { Ruleset, TableMember } from '../../../../api/types';
import type { NameLookup } from '../../../../hooks/usePublicNames';
import { SheetStats } from '../character/SheetStats';
import { HpBar } from './HpBar';
import { injuryName, injuryTiming, meFirst } from './statusView';

type Props = { members: TableMember[]; rules: Ruleset; myId: string | undefined; nameOf: NameLookup };

export function CharacterCards({ members, rules, myId, nameOf }: Props) {
  return (
    <ul className="plain-list status-cards">
      {meFirst(members, myId).map((member) => (
        <li key={member.user_id} className="status-card">
          <p className="status-card__name">{member.character?.name ?? '캐릭터를 정하지 않음'}</p>
          <p className="hint">
            {nameOf(member.user_id) ?? ''}
            {member.is_host ? ' · 방장' : ''}
            {member.user_id === myId ? ' · 나' : ''}
          </p>
          {member.sheet ? <SheetDetails member={member} rules={rules} /> : null}
          {member.fallen.length > 0 ? (
            <p className="hint">떠난 캐릭터: {member.fallen.map((fallen) => fallen.character_name).join(', ')}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function SheetDetails({ member, rules }: { member: TableMember; rules: Ruleset }) {
  const sheet = member.sheet;
  if (!sheet) return null;
  return (
    <>
      <HpBar sheet={sheet} rules={rules} />
      {sheet.injuries.length > 0 ? (
        <ul className="injuries" aria-label="부상">
          {sheet.injuries.map((injury) => (
            <li key={`${injury.injury}-${injury.round}`}>
              {injuryName(rules, injury.injury)} <span className="hint">({injuryTiming(injury, rules)})</span>
            </li>
          ))}
        </ul>
      ) : null}
      <details className="status-card__abilities">
        <summary>능력치</summary>
        <SheetStats rules={rules} abilities={sheet.abilities} maxHp={null} />
      </details>
    </>
  );
}
