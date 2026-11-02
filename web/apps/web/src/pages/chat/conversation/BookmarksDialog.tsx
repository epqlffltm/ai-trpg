// web/apps/web/src/pages/chat/conversation/BookmarksDialog.tsx
// 책갈피 창(#982). 단 책갈피를 나중에 단 것부터 보이고, 그 자리로 가고, 메모를 고치고, 뗀다.
// 그 자리로 가면 창을 닫는다. 다른 가지의 말이면 그 가지로 바꿔 보인다(부르는 쪽, onGo). chat 의 대화와 story 의 장면이 함께 쓴다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { BOOKMARK_NOTE_MAX, type Bookmark } from '../../../api/bookmarks';
import { bookmarkProblemText, bookmarkRoleLabel, bookmarksCountLabel } from './bookmarksView';
import type { BookmarkChange, BookmarksSource } from './useBookmarks';

type Props = {
  source: BookmarksSource;
  open: boolean;
  busy: boolean;
  onClose: () => void;
  /** 그 말의 자리로 간다(가지를 바꾸고 내린다) */
  onGo: (messageId: string) => void;
};

export function BookmarksDialog({ source, open, busy, onClose, onGo }: Props) {
  const { bookmarks, change } = source;
  const act = (request: BookmarkChange) => change.mutateAsync(request).then(() => true, () => false);
  const items = bookmarks.data ?? [];

  function go(messageId: string) {
    onClose();
    onGo(messageId);
  }

  return (
    <Dialog title="책갈피" open={open} onClose={onClose}>
      <div className="chat-notes">
        <p className="hint">좋았던 자리에 단 책갈피입니다. 눌러서 그 자리로 갑니다. 다른 가지의 말이면 그 가지가 보입니다.</p>
        {change.error ? <Notice tone="error">{bookmarkProblemText(change.error)}</Notice> : null}
        {bookmarks.isPending ? <p aria-busy="true">불러오는 중</p> : null}
        {bookmarks.isError ? <Notice tone="error">책갈피를 불러오지 못했습니다. 창을 닫았다 다시 열어 주세요.</Notice> : null}
        {bookmarks.isSuccess ? (
          <>
            <p className="hint">{bookmarksCountLabel(items)}</p>
            {items.length === 0 ? <p className="empty-state">아직 책갈피가 없습니다. 말 아래의 "책갈피"로 답니다.</p> : null}
            <ul className="plain-list chat-inventory" aria-label="책갈피">
              {items.map((bookmark) => (
                <BookmarkItem key={bookmark.message_id} bookmark={bookmark} busy={busy || change.isPending} onAct={act} onGo={go} />
              ))}
            </ul>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}

type ItemProps = { bookmark: Bookmark; busy: boolean; onAct: (request: BookmarkChange) => Promise<boolean>; onGo: (messageId: string) => void };

function BookmarkItem({ bookmark, busy, onAct, onGo }: ItemProps) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(bookmark.note ?? '');

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (await onAct({ kind: 'put', messageId: bookmark.message_id, note: note.trim() })) setEditing(false);
  }

  return (
    <li>
      <p>
        <span className="hint">{bookmarkRoleLabel(bookmark)} · </span>
        {bookmark.excerpt}
      </p>
      {bookmark.note && !editing ? <p className="hint">메모: {bookmark.note}</p> : null}
      {editing ? (
        <form onSubmit={(event) => void save(event)}>
          <label>
            메모
            <input value={note} maxLength={BOOKMARK_NOTE_MAX} onChange={(event) => setNote(event.target.value)} />
          </label>
          <Button type="submit" variant="secondary" disabled={busy}>
            저장
          </Button>
          <Button variant="quiet" onClick={() => setEditing(false)}>
            그만두기
          </Button>
        </form>
      ) : (
        <div className="actions">
          <Button variant="secondary" disabled={busy} onClick={() => onGo(bookmark.message_id)}>
            이 자리로
          </Button>
          <Button variant="quiet" onClick={() => setEditing(true)}>
            메모 고치기
          </Button>
          <Button variant="quiet" disabled={busy} onClick={() => void onAct({ kind: 'remove', messageId: bookmark.message_id })}>
            떼기
          </Button>
        </div>
      )}
    </li>
  );
}
