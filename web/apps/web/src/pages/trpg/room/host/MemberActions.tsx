// web/apps/web/src/pages/trpg/room/host/MemberActions.tsx
// 방장이 다른 사람에게 하는 일. 사람마다 내보내기, 방장 넘기기, "한 번 더 굴리기"(그럴 수 있을 때만).
// 내보내면 초대 코드가 새로 만들어진다. 새 코드를 알린다(내보낸 사람이 옛 코드로 다시 들어오지 못한다).

import { Button, Notice } from '@ai-trpg/ui';
import { useState } from 'react';
import { grantReroll, kickMember, transferHost } from '../../../../api/tableHost';
import type { TableDetail, TableMember } from '../../../../api/types';
import { ProblemNotice } from '../../../../components/ProblemNotice';
import { ConfirmButton } from '../../../../components/ConfirmButton';
import { canGrantReroll, otherMembers } from './hostView';
import { useHostAction } from './useHostAction';

type Props = { table: TableDetail; myId: string | undefined; nameOfMember: (userId: string) => string };

export function MemberActions({ table, myId, nameOfMember }: Props) {
  const [kicked, setKicked] = useState<{ name: string; code: string | null } | null>(null);
  const others = otherMembers(table, myId);
  if (others.length === 0) return <p className="hint">다른 사람이 아직 없습니다.</p>;
  return (
    <>
      {kicked ? (
        <Notice>
          {kicked.name}을(를) 내보냈습니다.{kicked.code ? ` 새 초대 코드는 ${kicked.code}입니다.` : ''}
        </Notice>
      ) : null}
      <ul className="plain-list host-members">
        {others.map((member) => (
          <MemberRow
            key={member.user_id}
            table={table}
            member={member}
            name={nameOfMember(member.user_id)}
            onKicked={(code) => setKicked({ name: nameOfMember(member.user_id), code })}
          />
        ))}
      </ul>
    </>
  );
}

type RowProps = { table: TableDetail; member: TableMember; name: string; onKicked: (code: string | null) => void };

function MemberRow({ table, member, name, onKicked }: RowProps) {
  const kick = useHostAction(table.id);
  const hand = useHostAction(table.id);
  const reroll = useHostAction(table.id);
  return (
    <li className="host-member">
      <span className="host-member__name">{name}</span>
      <span className="action-chips">
        {canGrantReroll(table, member) ? (
          <Button variant="quiet" aria-label={`${name}에게 한 번 더 굴리기`} busy={reroll.busy} onClick={() => void reroll.run(() => grantReroll(table.id, member.user_id))}>
            한 번 더 굴리기
          </Button>
        ) : null}
        <ConfirmButton
          label="방장 넘기기"
          ariaLabel={`${name}에게 방장 넘기기`}
          title="방장 넘기기"
          confirm="넘기기"
          busy={hand.busy}
          problem={hand.problem}
          onConfirm={async () => (await hand.run(() => transferHost(table.id, member.user_id))) !== null}
        >
          <p>{name}이(가) 방장이 됩니다. 시작, 라운드 닫기, 설정은 새 방장이 합니다.</p>
        </ConfirmButton>
        <ConfirmButton
          label="내보내기"
          ariaLabel={`${name} 내보내기`}
          title="내보내기"
          confirm="내보내기"
          busy={kick.busy}
          problem={kick.problem}
          onConfirm={async () => {
            const after = await kick.run(() => kickMember(table.id, member.user_id));
            if (after) onKicked(after.invite_code);
            return after !== null;
          }}
        >
          <p>{name}을(를) 테이블에서 내보냅니다. 초대 코드가 새로 만들어집니다. 진행 중이면 그 사람의 캐릭터는 이 판에서 빠집니다.</p>
        </ConfirmButton>
      </span>
      <ProblemNotice problem={reroll.problem} />
    </li>
  );
}
