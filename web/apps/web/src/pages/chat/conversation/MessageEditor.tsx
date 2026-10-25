// web/apps/web/src/pages/chat/conversation/MessageEditor.tsx
// 말 하나를 고치는 칸. 내 말이면 "고쳐 보내기"(새 가지로 답을 다시 받는다, 4000자), 상대의 말이면 "고치기"(그 자리에서, 20000자).
// 빈칸만 있는 글이나 바뀌지 않은 글은 보내지 않는다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ConversationMessage } from '../../../api/types';
import { TextAreaField } from '../../../components/TextAreaField';
import { MESSAGE_MAX } from './Composer';

/** 상대의 말을 고칠 때의 글자 수 상한(서버의 MessageEdit) */
export const ASSISTANT_EDIT_MAX = 20000;

type Props = { message: ConversationMessage; busy: boolean; onSubmit: (content: string) => void; onCancel: () => void };

export function MessageEditor({ message, busy, onSubmit, onCancel }: Props) {
  const [text, setText] = useState(message.content);
  const mine = message.role === 'user';
  const max = mine ? MESSAGE_MAX : ASSISTANT_EDIT_MAX;
  const changed = /\S/.test(text) && text !== message.content && text.length <= max;
  return (
    <form
      className="chat-message__editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (changed) onSubmit(text);
      }}
    >
      <TextAreaField
        label={mine ? '고쳐 보낼 말' : '고칠 글'}
        rows={4}
        maxLength={max}
        value={text}
        onChange={(event) => setText(event.target.value)}
        hint={mine ? '새 가지로 보내고 답을 다시 받습니다. 원래 말과 답은 대안으로 남습니다.' : '그 자리에서 고칩니다. 다음 답부터 고친 글을 봅니다.'}
      />
      <div className="chat-inventory__actions">
        <Button type="submit" disabled={busy || !changed}>
          {mine ? '고쳐 보내기' : '고치기'}
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          그만두기
        </Button>
      </div>
    </form>
  );
}
