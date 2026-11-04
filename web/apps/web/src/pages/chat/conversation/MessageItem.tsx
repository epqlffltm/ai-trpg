// web/apps/web/src/pages/chat/conversation/MessageItem.tsx
// 대사창의 말 하나. 말한 이, 글, 끊긴 답·고친 말의 표시, 받아들인 변화(호감도, 받은 물건, 함께 간 곳), 대안 사이 넘기기("< 2/3 >").
// 행동 말(이동, 건네기)은 이름 없이 서버가 쓴 글 그대로 보인다.
// 고치기: 내 말은 새 가지로 고쳐 보내고(답을 다시 받는다, 청구), 상대의 말은 그 자리에서 고친다(청구 없음, "고침" 표시).
// 행동 말은 서버가 쓴 글이라 고치지 않는다. 받는 중에는 고치지 못한다.
// 책갈피(#982)는 어느 말에나 달고 뗀다. 받는 중에도 된다(흘러 들어오는 답에는 없다).
// 장면 그림(#983)은 상대의 답에만 그린다. 그 대화에서 그리는 중이면 막는다. 그린 그림은 말 아래에 보인다.
// 단추에는 한 장의 값을 싣고, 그 서버에서 그릴 수 없으면(available 이 거짓) 단추를 숨긴다.

import { Button } from '@ai-trpg/ui';
import { useState } from 'react';
import type { Snapshot, SnapshotPrice } from '../../../api/snapshots';
import type { ConversationDetail, ConversationMessage } from '../../../api/types';
import { messageAnchor } from './bookmarksView';
import { BookmarkToggle } from './BookmarkToggle';
import { alternativeView, changeLines, speakerName } from './conversationView';
import { MessageEditor } from './MessageEditor';
import { MessageSnapshots, SnapshotButton } from './MessageSnapshots';
import { canOfferSnapshot } from './snapshotsView';

type Props = {
  message: ConversationMessage;
  detail: ConversationDetail;
  streaming: boolean;
  busy: boolean;
  onBranch: (messageId: string) => void;
  /** 고친 글을 보낸다. 받아들여졌으면 true(편집 칸을 닫는다) */
  onEdit: (message: ConversationMessage, content: string) => Promise<boolean>;
  /** 이 말에 책갈피가 있는가와 달고 떼기 */
  marked: boolean;
  onBookmark: (message: ConversationMessage) => void;
  /** 이 말의 장면 그림들, 한 장의 값(모르면 undefined), 새로 그리지 못하는가(그리는 중), 그리기 */
  snapshots: Snapshot[];
  drawPrice: SnapshotPrice | undefined;
  drawBlocked: boolean;
  onDraw: (messageId: string) => void;
};

export function MessageItem({ message, detail, streaming, busy, onBranch, onEdit, marked, onBookmark, snapshots, drawPrice, drawBlocked, onDraw }: Props) {
  const [editing, setEditing] = useState(false);
  const speaker = speakerName(message.role, detail);
  const changes = changeLines(message.changes ?? [], detail.character.document);
  const editable = message.role !== 'action' && !streaming;
  const drawable = message.role === 'assistant' && !streaming && message.content.trim() !== '' && canOfferSnapshot(drawPrice);

  async function submit(content: string) {
    if (await onEdit(message, content)) setEditing(false);
  }

  return (
    <li id={messageAnchor(message.id)} className={`chat-message chat-message--${message.role}`} aria-busy={streaming || undefined}>
      {speaker ? <p className="chat-message__speaker">{speaker}</p> : null}
      {editing ? (
        <MessageEditor message={message} busy={busy} onSubmit={(content) => void submit(content)} onCancel={() => setEditing(false)} />
      ) : (
        <p className="chat-message__content">{message.content}</p>
      )}
      <MessageMarks message={message} streaming={streaming} />
      {changes.length > 0 ? (
        <ul className="chat-message__changes" aria-label="바뀐 것">
          {changes.map((line, index) => (
            <li key={index}>{line}</li>
          ))}
        </ul>
      ) : null}
      <MessageSnapshots service="chat" snapshots={snapshots} />
      <div className="chat-message__tools">
        {streaming ? null : <Alternatives message={message} busy={busy} onBranch={onBranch} />}
        {editable && !editing ? (
          <Button variant="quiet" disabled={busy} aria-label={`${speaker ?? ''}의 말 고치기`} onClick={() => setEditing(true)}>
            고치기
          </Button>
        ) : null}
        {streaming ? null : <BookmarkToggle marked={marked} disabled={false} onToggle={() => onBookmark(message)} />}
        {drawable ? <SnapshotButton price={drawPrice} disabled={drawBlocked} onDraw={() => onDraw(message.id)} /> : null}
      </div>
    </li>
  );
}

function MessageMarks({ message, streaming }: { message: ConversationMessage; streaming: boolean }) {
  const marks = [streaming ? '쓰는 중' : null, !streaming && message.status === 'partial' ? '끊긴 답' : null, message.edited ? '고침' : null].filter(Boolean);
  if (marks.length === 0) return null;
  return <p className="hint chat-message__marks">{marks.join(' · ')}</p>;
}

function Alternatives({ message, busy, onBranch }: { message: ConversationMessage; busy: boolean; onBranch: (messageId: string) => void }) {
  const view = alternativeView(message);
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
