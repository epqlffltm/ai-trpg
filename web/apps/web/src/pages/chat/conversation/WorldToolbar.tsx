// web/apps/web/src/pages/chat/conversation/WorldToolbar.tsx
// 그림 창 아래의 단추들(C3): 소지품, 상대의 차림, 지도(판에 지도가 있을 때), 기억(C5), 시간 보내기, 기록 받기. 창은 겹쳐 연다.
// 행동(쓰기, 건네기, 이동, 시간 보내기)은 반응을 받으므로 받는 중이면 막는다. 창을 여는 것, 기억 고치기, 기록 받기는 막지 않는다.
// 시간 보내기는 다음 시간대가 시작하는 시각까지 흐른다(밤이면 다음 날 새벽 4시).

import { Button } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { ConversationAction, ConversationDetail } from '../../../api/types';
import { ChatTranscriptButton } from './ChatTranscriptButton';
import { InventoryDialog } from './InventoryDialog';
import { MapDialog } from './MapDialog';
import { NotesDialog } from './NotesDialog';
import { OutfitDialog } from './OutfitDialog';
import { hasMap } from './worldView';

type Window = 'inventory' | 'outfit' | 'map' | 'notes' | null;
type Props = { detail: ConversationDetail; busy: boolean; onAction: (action: ConversationAction) => void };

export function WorldToolbar({ detail, busy, onAction }: Props) {
  const [open, setOpen] = useState<Window>(null);
  // 창(Dialog)은 onClose 가 바뀌면 닫기 단추에 초점을 다시 둔다. 건네며 할 말을 쓰는 동안 초점이 튀지 않게 고정한다
  const close = useCallback(() => setOpen(null), []);

  function act(action: ConversationAction) {
    setOpen(null);
    onAction(action);
  }

  return (
    <div className="chat-toolbar" role="toolbar" aria-label="창과 행동">
      <Button variant="secondary" onClick={() => setOpen('inventory')}>
        소지품({detail.state.inventory.length})
      </Button>
      <Button variant="secondary" onClick={() => setOpen('outfit')}>
        차림
      </Button>
      {hasMap(detail.character.document) ? (
        <Button variant="secondary" onClick={() => setOpen('map')}>
          지도
        </Button>
      ) : null}
      <Button variant="secondary" onClick={() => setOpen('notes')}>
        기억
      </Button>
      <Button variant="secondary" disabled={busy} onClick={() => act({ kind: 'wait' })}>
        시간 보내기
      </Button>
      <ChatTranscriptButton conversationId={detail.id} title={detail.title} />
      <InventoryDialog detail={detail} open={open === 'inventory'} busy={busy} onClose={close} onAction={act} />
      <OutfitDialog detail={detail} open={open === 'outfit'} onClose={close} />
      <MapDialog detail={detail} open={open === 'map'} busy={busy} onClose={close} onAction={act} />
      <NotesDialog conversationId={detail.id} name={detail.character.document.name} open={open === 'notes'} onClose={close} />
    </div>
  );
}
