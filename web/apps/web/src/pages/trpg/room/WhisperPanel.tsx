// web/apps/web/src/pages/trpg/room/WhisperPanel.tsx
// 쪽지(B6 의 대화창, Stitch 20번의 "쪽지" 탭). 내 쪽지함의 끝부분(보낸 것과 받은 것)을 번호 차례로 보이고, 그 뒤는 스트림이 더한다.
// 쓰기: 받는 사람(같이 앉은 다른 사람)을 고르고 글을 써 보낸다. Enter 로 보내고 Shift+Enter 로 줄을 바꾼다.
// 길이와 빠르기의 한도는 채팅과 같다(서버가 채팅과 함께 센다). 쪽지는 보낸 사람과 받은 사람만 본다. 방장도 보지 못한다.
// GM(AI)에게 보여 주는 쪽지(gm_visible)는 아직 고르지 않는다(늘 보이지 않음). 끝난 테이블에는 쓸 수 없다. 읽기만 한다.

import { Button, Notice } from '@ai-trpg/ui';
import type { UseQueryResult } from '@tanstack/react-query';
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { postWhisper } from '../../../api/tableRoom';
import type { TableDetail, TableMember, Whisper, WhisperPage } from '../../../api/types';
import type { FormProblem } from '../../../auth/problem';
import { ProblemNotice } from '../../../components/ProblemNotice';
import type { NameLookup } from '../../../hooks/usePublicNames';
import { useCountdown } from '../../../hooks/useCountdown';
import { CHAT_MAX } from './ChatPanel';
import { displayName } from './MemberList';
import { describeWhisperProblem } from './roomProblem';

type Props = {
  table: TableDetail;
  whispers: UseQueryResult<WhisperPage>;
  myId: string | undefined;
  nameOf: NameLookup;
  onSent: (whisper: Whisper) => void;
};

export function WhisperPanel({ table, whispers, myId, nameOf, onSent }: Props) {
  const items = whispers.data?.items ?? [];
  const recipients = table.members.filter((member) => member.user_id !== myId);
  const writable = table.status !== 'ended';
  return (
    <section className="room-panel chat" aria-labelledby="whisper-heading">
      <h2 id="whisper-heading">쪽지</h2>
      {whispers.isPending ? <p>불러오는 중</p> : null}
      {whispers.isError ? (
        <Notice tone="error">
          쪽지를 불러오지 못했습니다.{' '}
          <Button variant="quiet" onClick={() => void whispers.refetch()}>
            다시 시도
          </Button>
        </Notice>
      ) : null}
      <WhisperList whispers={items} members={table.members} myId={myId} nameOf={nameOf} />
      {writable && recipients.length === 0 ? <p className="hint">쪽지를 보낼 사람이 아직 없습니다.</p> : null}
      {writable && recipients.length > 0 ? (
        <WhisperForm tableId={table.id} recipients={recipients} nameOf={nameOf} members={table.members} onSent={onSent} />
      ) : null}
    </section>
  );
}

type ListProps = { whispers: Whisper[]; members: TableMember[]; myId: string | undefined; nameOf: NameLookup };

function WhisperList({ whispers, members, myId, nameOf }: ListProps) {
  const end = useRef<HTMLLIElement>(null);
  const last = whispers.at(-1)?.sequence;
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'nearest' });
  }, [last]);
  if (whispers.length === 0) return <p className="hint">주고받은 쪽지가 없습니다.</p>;
  return (
    <ol className="chat__messages" aria-label="주고받은 쪽지" aria-live="polite">
      {whispers.map((whisper) => (
        <li key={whisper.sequence} className={whisper.sender_id === myId ? 'chat__message whisper whisper--sent' : 'chat__message whisper'}>
          <span className="chat__name">{whisperRoute(whisper, members, myId, nameOf)}</span>
          <span className="prose">{whisper.content}</span>
        </li>
      ))}
      <li ref={end} aria-hidden="true" className="chat__end" />
    </ol>
  );
}

/** 쪽지 한 줄의 머리. "렌 → 미아". 나는 "나"로 적는다. 캐릭터의 이름이 먼저고 없으면 닉네임 */
export function whisperRoute(whisper: Whisper, members: TableMember[], myId: string | undefined, nameOf: NameLookup): string {
  const sender = whisper.sender_id === myId ? '나' : (whisper.sender_character_name ?? displayName(whisper.sender_id, members, nameOf));
  const recipient =
    whisper.recipient_id === myId ? '나' : (whisper.recipient_character_name ?? displayName(whisper.recipient_id, members, nameOf));
  return `${sender} → ${recipient}`;
}

type FormProps = {
  tableId: string;
  recipients: TableMember[];
  members: TableMember[];
  nameOf: NameLookup;
  onSent: (whisper: Whisper) => void;
};

function WhisperForm({ tableId, recipients, members, nameOf, onSent }: FormProps) {
  const [recipientId, setRecipientId] = useState('');
  const [content, setContent] = useState('');
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<FormProblem | undefined>();
  const wait = useCountdown();
  const chosen = recipients.some((member) => member.user_id === recipientId);
  const sendable = chosen && content.trim() !== '' && content.length <= CHAT_MAX && wait.remaining === 0;

  async function send(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!sendable || busy) return;
    setBusy(true);
    setProblem(undefined);
    try {
      onSent(await postWhisper(tableId, recipientId, content));
      setContent('');
    } catch (error) {
      const next = describeWhisperProblem(error);
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
    <form className="chat__form whisper__form" onSubmit={send} noValidate>
      <ProblemNotice problem={problem} />
      <label className="visually-hidden" htmlFor="whisper-recipient">
        받는 사람
      </label>
      <select id="whisper-recipient" className="ui-field__input" value={recipientId} onChange={(event) => setRecipientId(event.target.value)}>
        <option value="" disabled>
          받는 사람 고르기
        </option>
        {recipients.map((member) => (
          <option key={member.user_id} value={member.user_id}>
            {member.character?.name ?? displayName(member.user_id, members, nameOf)}
          </option>
        ))}
      </select>
      <label className="visually-hidden" htmlFor="whisper-input">
        쪽지 쓰기
      </label>
      <textarea
        id="whisper-input"
        className="ui-field__input chat__input"
        rows={2}
        maxLength={CHAT_MAX}
        value={content}
        placeholder="고른 사람에게만 보이는 쪽지"
        onChange={(event) => setContent(event.target.value)}
        onKeyDown={keyDown}
      />
      <Button type="submit" busy={busy} disabled={!sendable}>
        {wait.remaining > 0 ? `${wait.remaining}초 뒤에` : '보내기'}
      </Button>
    </form>
  );
}
