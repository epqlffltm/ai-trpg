// web/apps/web/src/pages/chat/conversation/NotesDialog.tsx
// 기억 창(C5). 상대가 기억하는 것(기억 메모)을 보고 더하고 고치고 지운다. 요약이 제안한 메모는 따로 보이고 받아들이거나 버린다.
// 앞부분의 요약은 읽기만 한다. 메모는 다음 말부터 모델에 간다. 청구하지 않고, 답을 받는 중에도 고칠 수 있다.

import { Button, Dialog, Notice } from '@ai-trpg/ui';
import { useState, type FormEvent } from 'react';
import { NOTE_MAX, type MemoryNote } from '../../../api/chatNotes';
import { TextAreaField } from '../../../components/TextAreaField';
import { noteHint, noteProblemText, notesCountLabel, notesFull, sourceLabel, splitNotes } from './notesView';
import { useNotes, type NoteChange } from './useNotes';

type Props = { conversationId: string; name: string; open: boolean; onClose: () => void };

export function NotesDialog({ conversationId, name, open, onClose }: Props) {
  return (
    <Dialog title="기억" open={open} onClose={onClose}>
      {open ? <NotesBody conversationId={conversationId} name={name} /> : null}
    </Dialog>
  );
}

function NotesBody({ conversationId, name }: { conversationId: string; name: string }) {
  const { notes, summary, change } = useNotes(conversationId, true);
  const { kept, suggested } = splitNotes(notes.data ?? []);
  const full = notesFull(kept);
  const act = (request: NoteChange) => change.mutateAsync(request).then(() => true, () => false);

  return (
    <div className="chat-notes">
      <p className="hint">{name}이(가) 늘 기억하는 것입니다. 틀린 기억을 바로잡거나 기억할 것을 적습니다. 다음 말부터 들어가고 청구하지 않습니다.</p>
      {change.error ? <Notice tone="error">{noteProblemText(change.error)}</Notice> : null}
      {notes.isPending ? <p aria-busy="true">불러오는 중</p> : null}
      {notes.isError ? <Notice tone="error">메모를 불러오지 못했습니다. 창을 닫았다 다시 열어 주세요.</Notice> : null}
      {notes.isSuccess ? (
        <>
          <h3 className="chat-map__heading">
            기억 메모 <span className="hint">{notesCountLabel(kept)}</span>
          </h3>
          {kept.length === 0 ? <p className="empty-state">아직 메모가 없습니다. 상대가 기억할 것을 적어 주세요.</p> : null}
          <ul className="plain-list chat-inventory" aria-label="기억 메모">
            {kept.map((note) => (
              <NoteItem key={note.id} note={note} busy={change.isPending} onAct={act} />
            ))}
          </ul>
          {full ? <p className="hint">메모가 가득 찼습니다. 지운 뒤에 더합니다.</p> : <NewNote busy={change.isPending} onAdd={(text) => act({ kind: 'add', text })} />}
          {suggested.length > 0 ? (
            <>
              <h3 className="chat-map__heading">요약이 제안한 메모</h3>
              <p className="hint">받아들이면 다음 말부터 들어갑니다. 받아들이기 전에는 들어가지 않습니다.</p>
              <ul className="plain-list chat-inventory" aria-label="요약이 제안한 메모">
                {suggested.map((note) => (
                  <NoteItem key={note.id} note={note} busy={change.isPending} full={full} onAct={act} />
                ))}
              </ul>
            </>
          ) : null}
        </>
      ) : null}
      <SummaryText summary={summary.data ?? null} failed={summary.isError} />
    </div>
  );
}

type ItemProps = { note: MemoryNote; busy: boolean; full?: boolean; onAct: (request: NoteChange) => Promise<boolean> };

function NoteItem({ note, busy, full = false, onAct }: ItemProps) {
  const [editing, setEditing] = useState(false);
  if (editing) {
    return (
      <li>
        <NoteForm
          initial={note.text}
          label="고칠 메모"
          submitLabel="저장"
          busy={busy}
          onSubmit={async (text) => {
            if (await onAct({ kind: 'edit', id: note.id, text })) setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }
  return (
    <li>
      <p className="chat-message__content">{note.text}</p>
      <p className="hint">{sourceLabel(note)}</p>
      <div className="chat-inventory__actions">
        {note.pending ? (
          <Button variant="secondary" disabled={busy || full} onClick={() => void onAct({ kind: 'accept', id: note.id })}>
            받아들이기
          </Button>
        ) : null}
        <Button variant="quiet" disabled={busy} aria-label={`고치기: ${note.text}`} onClick={() => setEditing(true)}>
          고치기
        </Button>
        <Button variant="quiet" disabled={busy} aria-label={`${note.pending ? '버리기' : '지우기'}: ${note.text}`} onClick={() => void onAct({ kind: 'delete', id: note.id })}>
          {note.pending ? '버리기' : '지우기'}
        </Button>
      </div>
    </li>
  );
}

function NewNote({ busy, onAdd }: { busy: boolean; onAdd: (text: string) => Promise<boolean> }) {
  const [key, setKey] = useState(0);
  return (
    <NoteForm
      key={key}
      initial=""
      label="새 메모"
      submitLabel="더하기"
      busy={busy}
      onSubmit={async (text) => {
        if (await onAdd(text)) setKey((current) => current + 1);
      }}
    />
  );
}

type FormProps = { initial: string; label: string; submitLabel: string; busy: boolean; onSubmit: (text: string) => Promise<void>; onCancel?: () => void };

function NoteForm({ initial, label, submitLabel, busy, onSubmit, onCancel }: FormProps) {
  const [text, setText] = useState(initial);
  const hint = noteHint(text);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!hint && text !== initial) void onSubmit(text.trim());
  }

  return (
    <form className="chat-give" onSubmit={submit}>
      <TextAreaField label={label} rows={2} maxLength={NOTE_MAX} value={text} onChange={(event) => setText(event.target.value)} hint={`${text.length} / ${NOTE_MAX}자`} />
      <div className="chat-inventory__actions">
        <Button type="submit" disabled={busy || hint !== undefined || text === initial}>
          {submitLabel}
        </Button>
        {onCancel ? (
          <Button variant="quiet" onClick={onCancel}>
            그만두기
          </Button>
        ) : null}
      </div>
    </form>
  );
}

function SummaryText({ summary, failed }: { summary: { text: string } | null; failed: boolean }) {
  return (
    <>
      <h3 className="chat-map__heading">앞의 줄거리</h3>
      {failed ? <p className="hint">요약을 불러오지 못했습니다.</p> : null}
      {!failed && summary === null ? <p className="hint">아직 요약이 없습니다. 대화가 길어지면 앞부분을 요약해 기억합니다.</p> : null}
      {summary ? <p className="chat-message__content">{summary.text}</p> : null}
    </>
  );
}
