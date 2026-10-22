// web/apps/web/src/pages/trpg/room/round/DeclarationPanel.tsx
// 이번 라운드의 내 선언. 내지 않았으면 입력을, 냈으면 낸 것과 "고치기"를 보인다.
// 이번 라운드에 선언할 사람(waiting_for)도 아니고 낸 것도 없으면(새로 들어왔거나 죽었다) 입력을 보이지 않는다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Round, Ruleset } from '../../../../api/types';
import { DeclarationForm } from './DeclarationForm';
import { actionLabel, myDeclaration } from './roundView';

type Props = { tableId: string; round: Round; rules: Ruleset; myId: string | undefined };

export function DeclarationPanel({ tableId, round, rules, myId }: Props) {
  const [editing, setEditing] = useState(false);
  const mine = myDeclaration(round, myId);
  const expected = myId !== undefined && round.waiting_for.includes(myId);
  if (!mine && !expected) return <p className="hint">이번 라운드에는 선언하지 않습니다.</p>;
  if (mine && !editing) {
    return (
      <div className="my-declaration">
        <p className="waiting-room__label">내 선언</p>
        <p className="prose">{mine.content}</p>
        {mine.action ? <p className="hint">{actionLabel(mine.action, rules)}</p> : null}
        <Button variant="secondary" onClick={() => setEditing(true)}>
          고치기
        </Button>
      </div>
    );
  }
  return (
    <DeclarationForm
      tableId={tableId}
      rules={rules}
      mine={mine}
      onDone={() => setEditing(false)}
      onCancel={mine ? () => setEditing(false) : undefined}
    />
  );
}
