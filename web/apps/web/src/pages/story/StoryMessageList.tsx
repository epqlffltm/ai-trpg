// web/apps/web/src/pages/story/StoryMessageList.tsx
// 대사창(D2 의 아래). 지금 가지의 말들과 흘러 들어오는 답. 답은 말 조각마다 이름표(서술은 이름표 없음)를 붙인다.
// 사람의 말은 "나", 행동 말은 서버가 쓴 글 그대로다(엔진이 정한 결과다). 새 글이 오면 끝으로 내린다.
// 끝의 말에 할 수 있는 일(답 받기, 다시 생성, 이어서)과 대안 넘기기, 고치기(내 말은 새 가지로, 답은 조각마다 그 자리에서)는 여기 둔다.
// 행동 말은 엔진의 결과라 고치지 않는다. 받는 중에는 모두 막는다.

import { Button } from '@ai-trpg/ui';
import { useEffect, useRef, useState } from 'react';
import type { StoryMessage, StorySegment, StorySession, StoryView } from '../../api/story';
import { StoryMessageEditor } from './StoryMessageEditor';
import { storyAlternatives, storyTail, visibleStoryMessages } from './storyView';
import { speakerName } from './storyWorld';
import type { StoryTurnState } from './storyTurnState';

type Props = {
  session: StorySession;
  turn: StoryTurnState | null;
  busy: boolean;
  onBranch: (messageId: string) => void;
  onRegenerate: (messageId: string) => void;
  onContinue: (messageId: string) => void;
  /** 내 말을 고쳐 새 가지로 보낸다. 받아들여졌으면 true */
  onSendEdit: (message: StoryMessage, content: string) => Promise<boolean>;
  /** 답의 조각을 그 자리에서 고친다. 고쳤으면 true */
  onSaveSegments: (message: StoryMessage, segments: string[]) => Promise<boolean>;
};

export function StoryMessageList({ session, turn, busy, onBranch, onRegenerate, onContinue, onSendEdit, onSaveSegments }: Props) {
  const { items, pending, streamingId } = visibleStoryMessages(session.messages, turn);
  const end = useRef<HTMLDivElement>(null);
  const growth = items.length + (pending?.reduce((sum, segment) => sum + segment.text.length + 1, 0) ?? 0);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [growth]);
  const view = session.view;

  return (
    <section className="conversation__log" aria-label="이야기">
      {items.length === 0 && pending === null ? <p className="hint">첫 말을 걸어 이야기를 시작하세요.</p> : null}
      <ol className="plain-list chat-messages" aria-label="말">
        {items.map((message) => (
          <StoryMessageItem
            key={message.id}
            message={message}
            view={view}
            streaming={message.id === streamingId}
            busy={busy}
            onBranch={onBranch}
            onSendEdit={(content) => onSendEdit(message, content)}
            onSaveSegments={(segments) => onSaveSegments(message, segments)}
          />
        ))}
        {pending !== null ? (
          <li className="chat-message chat-message--assistant" aria-busy="true">
            <Segments segments={pending} view={view} />
            {pending.length === 0 ? <p className="chat-message__content">…</p> : null}
            <p className="hint chat-message__marks">쓰는 중</p>
          </li>
        ) : null}
      </ol>
      {turn ? null : <TailActions messages={session.messages} busy={busy} onRegenerate={onRegenerate} onContinue={onContinue} />}
      <div ref={end} />
    </section>
  );
}

type ItemProps = {
  message: StoryMessage;
  view: StoryView;
  streaming: boolean;
  busy: boolean;
  onBranch: (messageId: string) => void;
  onSendEdit: (content: string) => Promise<boolean>;
  onSaveSegments: (segments: string[]) => Promise<boolean>;
};

function StoryMessageItem({ message, view, streaming, busy, onBranch, onSendEdit, onSaveSegments }: ItemProps) {
  const [editing, setEditing] = useState(false);
  const marks = [streaming ? '쓰는 중' : null, !streaming && message.status === 'partial' ? '끊긴 답' : null, message.edited ? '고침' : null].filter(Boolean);
  const editable = message.role !== 'action' && !streaming;

  async function finish(done: Promise<boolean>) {
    if (await done) setEditing(false);
  }

  if (editing) {
    return (
      <li className={`chat-message chat-message--${message.role}`}>
        <StoryMessageEditor
          message={message}
          view={view}
          busy={busy}
          onSendEdit={(content) => void finish(onSendEdit(content))}
          onSaveSegments={(segments) => void finish(onSaveSegments(segments))}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  return (
    <li className={`chat-message chat-message--${message.role}`} aria-busy={streaming || undefined}>
      {message.role === 'assistant' ? (
        <Segments segments={message.segments} view={view} />
      ) : (
        <>
          {message.role === 'user' ? <p className="chat-message__speaker">나</p> : null}
          <p className="chat-message__content">{message.content}</p>
        </>
      )}
      {marks.length > 0 ? <p className="hint chat-message__marks">{marks.join(' · ')}</p> : null}
      <div className="chat-message__tools">
        {streaming ? null : <Alternatives message={message} busy={busy} onBranch={onBranch} />}
        {editable ? (
          <Button variant="quiet" disabled={busy} aria-label={message.role === 'user' ? '내 말 고치기' : '이 답 고치기'} onClick={() => setEditing(true)}>
            고치기
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function Segments({ segments, view }: { segments: StorySegment[]; view: StoryView }) {
  return (
    <>
      {segments.map((segment, index) => {
        const name = speakerName(view, segment.speaker);
        return (
          <div key={index} className={name ? 'story-segment' : 'story-segment story-segment--narration'}>
            {name ? <p className="chat-message__speaker">{name}</p> : null}
            <p className="chat-message__content">{segment.text}</p>
          </div>
        );
      })}
    </>
  );
}

function Alternatives({ message, busy, onBranch }: { message: StoryMessage; busy: boolean; onBranch: (messageId: string) => void }) {
  const view = storyAlternatives(message);
  if (!view) return null;
  return (
    <div className="chat-message__alternatives">
      <Button variant="quiet" aria-label="앞의 대안" disabled={busy || !view.previous} onClick={() => view.previous && onBranch(view.previous)}>
        ‹
      </Button>
      <span>
        {view.position}/{view.count}
      </span>
      <Button variant="quiet" aria-label="뒤의 대안" disabled={busy || !view.next} onClick={() => view.next && onBranch(view.next)}>
        ›
      </Button>
    </div>
  );
}

type TailProps = { messages: StoryMessage[]; busy: boolean; onRegenerate: (messageId: string) => void; onContinue: (messageId: string) => void };

function TailActions({ messages, busy, onRegenerate, onContinue }: TailProps) {
  const tail = storyTail(messages);
  if (!tail.answer && !tail.regenerate && !tail.continueFrom) return null;
  return (
    <div className="chat-tail">
      {tail.continueFrom ? (
        <Button variant="secondary" disabled={busy} onClick={() => onContinue(tail.continueFrom as string)}>
          이어서
        </Button>
      ) : null}
      {tail.answer ? (
        <Button variant="secondary" disabled={busy} onClick={() => onRegenerate(tail.answer as string)}>
          답 받기
        </Button>
      ) : null}
      {tail.regenerate ? (
        <Button variant="quiet" disabled={busy} onClick={() => onRegenerate(tail.regenerate as string)}>
          다시 생성
        </Button>
      ) : null}
    </div>
  );
}
