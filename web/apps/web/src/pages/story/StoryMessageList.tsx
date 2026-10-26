// web/apps/web/src/pages/story/StoryMessageList.tsx
// 대사창(D2 의 아래). 지금 가지의 말들과 흘러 들어오는 답. 답은 말 조각마다 이름표(서술은 이름표 없음)를 붙인다.
// 사람의 말은 "나", 행동 말은 서버가 쓴 글 그대로다(엔진이 정한 결과다). 새 글이 오면 끝으로 내린다.
// 끝의 말에 할 수 있는 일(답 받기, 다시 생성)과 대안 넘기기는 여기 둔다. 받는 중에는 모두 막는다.

import { Button } from '@ai-trpg/ui';
import { useEffect, useRef } from 'react';
import type { StoryMessage, StorySegment, StorySession } from '../../api/story';
import { storyAlternatives, storyTail, visibleStoryMessages } from './storyView';
import { speakerName } from './storyWorld';
import type { StoryTurnState } from './storyTurnState';

type Props = {
  session: StorySession;
  turn: StoryTurnState | null;
  busy: boolean;
  onBranch: (messageId: string) => void;
  onRegenerate: (messageId: string) => void;
};

export function StoryMessageList({ session, turn, busy, onBranch, onRegenerate }: Props) {
  const { items, pending } = visibleStoryMessages(session.messages, turn);
  const end = useRef<HTMLDivElement>(null);
  const growth = items.length + (pending?.reduce((sum, segment) => sum + segment.text.length + 1, 0) ?? 0);
  useEffect(() => {
    end.current?.scrollIntoView?.({ block: 'end' });
  }, [growth]);
  const document = session.world.document;

  return (
    <section className="conversation__log" aria-label="이야기">
      {items.length === 0 && pending === null ? <p className="hint">첫 말을 걸어 이야기를 시작하세요.</p> : null}
      <ol className="plain-list chat-messages" aria-label="말">
        {items.map((message) => (
          <StoryMessageItem key={message.id} message={message} document={document} busy={busy} onBranch={onBranch} />
        ))}
        {pending !== null ? (
          <li className="chat-message chat-message--assistant" aria-busy="true">
            <Segments segments={pending} document={document} />
            {pending.length === 0 ? <p className="chat-message__content">…</p> : null}
            <p className="hint chat-message__marks">쓰는 중</p>
          </li>
        ) : null}
      </ol>
      {turn ? null : <TailActions messages={session.messages} busy={busy} onRegenerate={onRegenerate} />}
      <div ref={end} />
    </section>
  );
}

type ItemProps = { message: StoryMessage; document: Record<string, unknown>; busy: boolean; onBranch: (messageId: string) => void };

function StoryMessageItem({ message, document, busy, onBranch }: ItemProps) {
  const marks = [message.status === 'partial' ? '끊긴 답' : null, message.edited ? '고침' : null].filter(Boolean);
  return (
    <li className={`chat-message chat-message--${message.role}`}>
      {message.role === 'assistant' ? (
        <Segments segments={message.segments} document={document} />
      ) : (
        <>
          {message.role === 'user' ? <p className="chat-message__speaker">나</p> : null}
          <p className="chat-message__content">{message.content}</p>
        </>
      )}
      {marks.length > 0 ? <p className="hint chat-message__marks">{marks.join(' · ')}</p> : null}
      <Alternatives message={message} busy={busy} onBranch={onBranch} />
    </li>
  );
}

function Segments({ segments, document }: { segments: StorySegment[]; document: Record<string, unknown> }) {
  return (
    <>
      {segments.map((segment, index) => {
        const name = speakerName(document, segment.speaker);
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

function TailActions({ messages, busy, onRegenerate }: { messages: StoryMessage[]; busy: boolean; onRegenerate: (messageId: string) => void }) {
  const tail = storyTail(messages);
  if (!tail.answer && !tail.regenerate) return null;
  return (
    <div className="chat-tail">
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
