// web/apps/web/src/pages/trpg/room/round/DeclarationPanel.tsx
// 이번 라운드의 내 선언. 내지 않았으면 입력을, 냈으면 낸 것과 "고치기"를 보인다.
// 이번 라운드에 선언할 사람(waiting_for)도 아니고 낸 것도 없으면(새로 들어왔거나 죽었다) 입력을 보이지 않는다.
// 차례대로 진행하는 테이블(#287)에서는 차례의 주인만 선언한다. 다른 사람에게는 누구의 차례인지 보인다.
// 상태 패널이 행동을 부탁하면(action/actionRequest.tsx) 낸 것을 보던 중이어도 입력을 연다.
// 모양은 Stitch 20번의 선언 칸: 머리에 "행동 선언"과 오른쪽에 "마감 전까지 고칠 수 있습니다", 그 아래 입력이나 낸 것.

import { Button } from '@ai-trpg/ui';
import { useId, useState, type ReactNode } from 'react';
import type { Round, TableDetail } from '../../../../api/types';
import { useActionRequests } from './action/actionRequest';
import { DeclarationForm } from './DeclarationForm';
import { actionLabel, myDeclaration, notDeclaringText } from './roundView';

type Props = {
  table: TableDetail;
  round: Round;
  myId: string | undefined;
  nameOfMember: (userId: string) => string;
};

export function DeclarationPanel({ table, round, myId, nameOfMember }: Props) {
  const [editing, setEditing] = useState(false);
  const { pending } = useActionRequests();
  const mine = myDeclaration(round, myId);
  const me = table.members.find((member) => member.user_id === myId);
  const expected = myId !== undefined && round.waiting_for.includes(myId);

  if (!me || (!mine && !expected)) return <p className="hint">{notDeclaringText(table, round, myId, nameOfMember)}</p>;
  if (mine && !editing && !pending) {
    return (
      <DeclareBox>
        <div className="my-declaration">
          <p className="waiting-room__label">내 선언</p>
          <p className="prose">{mine.content}</p>
          {mine.action ? <p className="hint">{actionLabel(mine.action, table)}</p> : null}
          <Button variant="secondary" onClick={() => setEditing(true)}>
            고치기
          </Button>
        </div>
      </DeclareBox>
    );
  }
  return (
    <DeclareBox>
      <DeclarationForm
        table={table}
        me={me}
        mine={mine}
        onDone={() => setEditing(false)}
        onCancel={mine ? () => setEditing(false) : undefined}
        onRequest={() => setEditing(true)}
      />
    </DeclareBox>
  );
}

/** 선언 칸의 틀. 머리와 그 아래 내용 */
function DeclareBox({ children }: { children: ReactNode }) {
  const headingId = useId();
  return (
    <section className="declare-box" aria-labelledby={headingId}>
      <div className="declare-box__head">
        <h4 id={headingId}>행동 선언</h4>
        <p className="hint">마감 전까지 고칠 수 있습니다.</p>
      </div>
      {children}
    </section>
  );
}
