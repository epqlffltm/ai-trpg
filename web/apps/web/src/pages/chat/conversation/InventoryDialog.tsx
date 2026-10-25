// web/apps/web/src/pages/chat/conversation/InventoryDialog.tsx
// 소지품 창(C3). 가진 물건과 수, 설명. 물건마다 "쓰기"와 "건네기"(한마디를 덧붙일 수 있다. 비우면 행동만).
// 쓰면 없어지는 물건(음식 등)은 하나 줄고, 옷을 건네면 상대가 입는다. 무엇이 바뀌는지는 서버가 정한다. 행동마다 반응을 한 번 받는다(청구).

import { Button, Dialog } from '@ai-trpg/ui';
import { useState } from 'react';
import type { ConversationAction, ConversationDetail } from '../../../api/types';
import { TextAreaField } from '../../../components/TextAreaField';
import { MESSAGE_MAX } from './Composer';
import { inventoryRows, type InventoryRow } from './worldView';

type Props = { detail: ConversationDetail; open: boolean; busy: boolean; onClose: () => void; onAction: (action: ConversationAction) => void };

export function InventoryDialog({ detail, open, busy, onClose, onAction }: Props) {
  const rows = inventoryRows(detail.state.inventory, detail.character.document);
  const [giving, setGiving] = useState<string | null>(null);

  function act(action: ConversationAction) {
    setGiving(null);
    onAction(action);
  }

  return (
    <Dialog title="소지품" open={open} onClose={onClose}>
      {rows.length === 0 ? <p className="empty-state">가진 물건이 없습니다.</p> : null}
      <ul className="plain-list chat-inventory" aria-label="가진 물건">
        {rows.map((row) => (
          <li key={row.id}>
            <ItemLine row={row} />
            {giving === row.id ? (
              <GiveForm row={row} busy={busy} onGive={(words) => act(words ? { kind: 'give', item: row.id, words } : { kind: 'give', item: row.id })} onCancel={() => setGiving(null)} />
            ) : (
              <div className="chat-inventory__actions">
                <Button variant="secondary" disabled={busy} onClick={() => act({ kind: 'use', item: row.id })}>
                  {row.name} 쓰기
                </Button>
                <Button variant="secondary" disabled={busy} onClick={() => setGiving(row.id)}>
                  {row.name} 건네기
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </Dialog>
  );
}

function ItemLine({ row }: { row: InventoryRow }) {
  const marks = [row.count > 1 ? `${row.count}개` : null, row.consumable ? '쓰면 없어짐' : null, row.clothing ? '옷' : null].filter(Boolean).join(' · ');
  return (
    <div>
      <p className="chat-inventory__name">
        {row.name} {marks ? <span className="hint">{marks}</span> : null}
      </p>
      {row.description ? <p className="hint">{row.description}</p> : null}
    </div>
  );
}

function GiveForm({ row, busy, onGive, onCancel }: { row: InventoryRow; busy: boolean; onGive: (words: string) => void; onCancel: () => void }) {
  const [words, setWords] = useState('');
  return (
    <form
      className="chat-give"
      onSubmit={(event) => {
        event.preventDefault();
        onGive(words.trim());
      }}
    >
      <TextAreaField label={`${row.name}을(를) 건네며 할 말(비우면 건네기만)`} rows={2} maxLength={MESSAGE_MAX} value={words} onChange={(event) => setWords(event.target.value)} />
      <div className="chat-inventory__actions">
        <Button type="submit" disabled={busy}>
          건네기
        </Button>
        <Button variant="quiet" onClick={onCancel}>
          그만두기
        </Button>
      </div>
    </form>
  );
}
