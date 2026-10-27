// web/apps/web/src/pages/story/StoryMessageEditor.tsx
// 말 하나를 고치는 칸(D2). 내 말이면 한 칸(4000자, "고쳐 보내기": 새 가지로 답을 다시 받는다, 청구).
// 답이면 조각마다 한 칸(이름표는 그대로, 한 줄씩, "고치기": 그 자리에서, 청구 없음). 말하는 사람과 조각의 수는 바꾸지 못한다(서버의 규칙).
// 빈칸만 있는 글, 줄바꿈, 바뀌지 않은 글은 보내지 않는다.

import { Button, TextField } from '@ai-trpg/ui';
import { useState } from 'react';
import type { StoryMessage, StoryView } from '../../api/story';
import { TextAreaField } from '../../components/TextAreaField';
import { MESSAGE_MAX } from '../chat/conversation/Composer';
import { canSaveSegments, canSendEdit } from './storyEdit';
import { speakerName } from './storyWorld';

type Props = {
  message: StoryMessage;
  view: StoryView;
  busy: boolean;
  onSendEdit: (content: string) => void;
  onSaveSegments: (segments: string[]) => void;
  onCancel: () => void;
};

export function StoryMessageEditor({ message, view, busy, onSendEdit, onSaveSegments, onCancel }: Props) {
  return message.role === 'user' ? (
    <UserEditor message={message} busy={busy} onSubmit={onSendEdit} onCancel={onCancel} />
  ) : (
    <AnswerEditor message={message} view={view} busy={busy} onSubmit={onSaveSegments} onCancel={onCancel} />
  );
}

function UserEditor({ message, busy, onSubmit, onCancel }: { message: StoryMessage; busy: boolean; onSubmit: (content: string) => void; onCancel: () => void }) {
  const [text, setText] = useState(message.content);
  const ok = canSendEdit(message.content, text);
  return (
    <form
      className="chat-message__editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (ok) onSubmit(text);
      }}
    >
      <TextAreaField
        label="고쳐 보낼 말"
        rows={3}
        maxLength={MESSAGE_MAX}
        value={text}
        onChange={(event) => setText(event.target.value)}
        hint="새 가지로 보내고 답을 다시 받습니다. 원래 말과 답은 대안으로 남습니다."
      />
      <EditorActions submitLabel="고쳐 보내기" disabled={busy || !ok} onCancel={onCancel} />
    </form>
  );
}

function AnswerEditor({ message, view, busy, onSubmit, onCancel }: { message: StoryMessage; view: StoryView; busy: boolean; onSubmit: (segments: string[]) => void; onCancel: () => void }) {
  const [texts, setTexts] = useState(() => message.segments.map((segment) => segment.text));
  const ok = canSaveSegments(message.segments, texts);
  return (
    <form
      className="chat-message__editor"
      onSubmit={(event) => {
        event.preventDefault();
        if (ok) onSubmit(texts);
      }}
    >
      {message.segments.map((segment, index) => (
        <TextField
          key={index}
          label={speakerName(view, segment.speaker) ?? '서술'}
          maxLength={MESSAGE_MAX}
          value={texts[index] ?? ''}
          onChange={(event) => setTexts((current) => current.map((text, at) => (at === index ? event.target.value.replace(/[\r\n]+/g, ' ') : text)))}
        />
      ))}
      <p className="hint">그 자리에서 고칩니다. 말하는 사람과 조각의 수는 그대로이고, 다음 답부터 고친 글을 봅니다.</p>
      <EditorActions submitLabel="고치기" disabled={busy || !ok} onCancel={onCancel} />
    </form>
  );
}

function EditorActions({ submitLabel, disabled, onCancel }: { submitLabel: string; disabled: boolean; onCancel: () => void }) {
  return (
    <div className="chat-inventory__actions">
      <Button type="submit" disabled={disabled}>
        {submitLabel}
      </Button>
      <Button variant="quiet" onClick={onCancel}>
        그만두기
      </Button>
    </div>
  );
}
