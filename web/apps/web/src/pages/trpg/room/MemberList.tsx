// web/apps/web/src/pages/trpg/room/MemberList.tsx
// 앉은 사람들. 캐릭터의 이름(정하지 않았으면 그렇게), 사람의 닉네임, 방장, 나.
// HP, 부상, 소지품은 상태 패널(B7)에서 보인다.

import type { TableMember } from '../../../api/types';
import type { NameLookup } from '../../../hooks/usePublicNames';

type Props = { members: TableMember[]; myId: string | undefined; nameOf: NameLookup };

export function MemberList({ members, myId, nameOf }: Props) {
  return (
    <section className="room-panel" aria-labelledby="members-heading">
      <h2 id="members-heading">앉은 사람</h2>
      <ul className="plain-list members">
        {members.map((member) => (
          <li key={member.user_id} className="member">
            <span className="member__character">{member.character?.name ?? '캐릭터를 정하지 않음'}</span>
            <span className="hint">
              {nameOf(member.user_id) ?? ''}
              {member.is_host ? ' · 방장' : ''}
              {member.user_id === myId ? ' · 나' : ''}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** 모두 캐릭터를 정했는가. 시작 단추를 켜는 데 쓴다(맞는지는 서버가 다시 본다) */
export function everyoneHasCharacter(members: TableMember[]): boolean {
  return members.length > 0 && members.every((member) => member.character !== null);
}

/** 채팅과 입력 중에 보일 이름. 캐릭터의 이름이 먼저고, 없으면 닉네임 */
export function displayName(userId: string, members: TableMember[], nameOf: NameLookup): string {
  const member = members.find((candidate) => candidate.user_id === userId);
  return member?.character?.name ?? nameOf(userId) ?? '누군가';
}
