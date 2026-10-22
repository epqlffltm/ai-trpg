// web/apps/web/src/pages/trpg/room/ChatPanel.tsx
// 판 채팅. 지난 것은 끝부분(50줄)만 읽고, 그 뒤는 스트림이 더한다. 이름은 캐릭터의 이름이 먼저고 없으면 닉네임.
// 쓰기: Enter 로 보내고 Shift+Enter 로 줄을 바꾼다. 500자까지. 너무 빨리 쓰면(10초에 5줄) 기다리게 한다.
// 입력 중: 글자를 치는 동안 3초에 한 번만 알린다(실패해도 그만). 받는 쪽이 5초 뒤에 스스로 지운다.
// 끝난 테이블에는 쓸 수 없다. 읽기만 한다.

import { Button, Notice } from '@ai-trpg/ui';
import type { UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { announceTyping, postMessage } from '../../../api/tableRoom';
import type { ChatMessage, MessagePage, TableDetail, TableMember } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import type { NameLookup } from '../../../hooks/usePublicNames';
import { useCountdown } from '../../../hooks/useCountdown';
import { displayName } from './MemberList';
import { describeChatProblem } from './roomProblem';

/** 채팅 한 줄의 최대 길이(서버의 MessageCreate) */
export const CHAT_MAX = 500;
/** 입력 중을 알리는 간격 */
export const TYPING_EVERY_MS = 3000;

type Props = {
  table: TableDetail;
  chat: UseQueryResult<MessagePage>;
  members: TableMember[];
  nameOf: NameLookup;
  typingIds: string[];
  onSent: (message: ChatMessage) => void;
};

export function ChatPanel({ table, chat, members, nameOf, typingIds, onSent }: Props) {
  const messages = chat.data?.items ?? [];
  const writable = table.status !== 'ended';
  return (
    <section className="room-panel chat" aria-labelledby="chat-heading">
      <h2 id="chat-heading">채팅</h2>
      {chat.isPending ? <p>불러오는 중</p> : null}
      {chat.isError ? (
        <Notice tone="error">
          채팅을 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void chat.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      <MessageList messages={messages} members={members} nameOf={nameOf} />
      <TypingLine typingIds={typingIds} members={members} nameOf={nameOf} />
      {writable ? <ChatForm tableId={table.id} onSent={onSent} /> : null}
    </section>
  );
}

function MessageList({ messages, members, nameOf }: { messages: ChatMessage[]; members: TableMember[]; nameOf: NameLookup }) {
  const end = useRef<HTMLLIElement>(null);
  const last = messages.at(-1)?.sequence;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' });
  }, [last]);
  if (messages.length === 0) return <p className="hint">아직 채팅이 없습니다.</p>;
  return (
    <ol className="chat__messages" aria-live="polite">
      {messages.map((message) => (
        <li key={message.sequence} className="chat__message">
          <span className="chat__name">{message.character_name ?? displayName(message.user_id, members, nameOf)}</span>
          <span className="prose">{message.content}</span>
        </li>
      ))}
      <li ref={end} aria-hidden="true" className="chat__end" />
    </ol>
  );
}

function TypingLine({ typingIds, members, nameOf }: { typingIds: string[]; members: TableMember[]; nameOf: NameLookup }) {
  if (typingIds.length === 0) return null;
  const names = typingIds.map((userId) => displayName(userId, members, nameOf));
  return <p className="hint chat__typing">{names.join(', ')} 님이 입력하는 중</p>;
}

function ChatForm({ tableId, onSent }: { tableId: string; onSent: (message: ChatMessage) => void }) {
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const lastTyping = useRef(0);
  const wait = useCountdown();
  const sendable = content.trim() !== '' && content.length <= CHAT_MAX && wait.remaining === 0;

  function typed(value: string) {
    setContent(value);
    const now = Date.now();
    if (value.trim() && now - lastTyping.current >= TYPING_EVERY_MS) {
      lastTyping.current = now;
      void announceTyping(tableId).catch(() => undefined);
    }
  }

  async function send(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!sendable || busy) return;
    setBusy(true);
    setProblem(undefined);
    try {
      onSent(await postMessage(tableId, content));
      setContent('');
      lastTyping.current = 0;
    } catch (error) {
      const next = describeChatProblem(error);
      setProblem(next);
      if (next.waitSeconds) wait.start(next.waitSeconds);
    }
    setBusy(false);
  }

  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <form className="chat__form" onSubmit={send} noValidate>
      <ProblemNotice problem={problem} />
      <label className="visually-hidden" htmlFor="chat-input">
        채팅 쓰기
      </label>
      <textarea
        id="chat-input"
        className="ui-field__input chat__input"
        rows={2}
        maxLength={CHAT_MAX}
        value={content}
        placeholder="같이 앉은 사람과 이야기하기"
        onChange={(event) => typed(event.target.value)}
        onKeyDown={keyDown}
      />
      <Button type="submit" busy={busy} disabled={!sendable}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에` : '보내기'}
      </Button>
    </form>
  );
}
