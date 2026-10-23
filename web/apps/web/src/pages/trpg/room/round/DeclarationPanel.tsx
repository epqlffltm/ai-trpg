// web/apps/web/src/pages/trpg/room/round/DeclarationPanel.tsx
// 이번 라운드의 내 선언. 내지 않았으면 입력을, 냈으면 낸 것과 "고치기"를 보인다.
// 이번 라운드에 선언할 사람(waiting_for)도 아니고 낸 것도 없으면(새로 들어왔거나 죽었다) 입력을 보이지 않는다.
// 상태 패널이 행동을 부탁하면(action/actionRequest.tsx) 낸 것을 보던 중이어도 입력을 연다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Round, TableDetail } from '../../../../api/types';
import { useActionRequests } from './action/actionRequest';
import { DeclarationForm } from './DeclarationForm';
import { actionLabel, myDeclaration } from './roundView';

type Props = { table: TableDetail; round: Round; myId: string | undefined };

export function DeclarationPanel({ table, round, myId }: Props) {
  const [editing, setEditing] = useState(false);
  const { pending } = useActionRequests();
  const mine = myDeclaration(round, myId);
  const me = table.members.find((member) => member.user_id === myId);
  const expected = myId !== undefined && round.waiting_for.includes(myId);

  if (!me || (!mine && !expected)) return <p className="hint">이번 라운드에는 선언하지 않습니다.</p>;
  if (mine && !editing && !pending) {
    return (
      <div className="my-declaration">
        <p className="waiting-room__label">내 선언</p>
        <p className="prose">{mine.content}</p>
        {mine.action ? <p className="hint">{actionLabel(mine.action, table)}</p> : null}
        <Button variant="secondary" onClick={() => setEditing(true)}>
          고치기
        </Button>
      </div>
    );
  }
  return (
    <DeclarationForm
      table={table}
      me={me}
      mine={mine}
      onDone={() => setEditing(false)}
      onCancel={mine ? () => setEditing(false) : undefined}
      onRequest={() => setEditing(true)}
    />
  );
}
