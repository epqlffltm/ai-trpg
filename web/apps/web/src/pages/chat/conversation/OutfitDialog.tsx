// web/apps/web/src/pages/chat/conversation/OutfitDialog.tsx
// 상대의 차림 창(C3). 상대가 지금 입은 옷(내가 건넨 옷)을 입은 차례대로 보인다. 없으면 처음 차림 그대로다.

import { Dialog } from '@ai-trpg/ui';
import type { ConversationDetail } from '../../../api/types';
import { outfitNames } from './worldView';

export function OutfitDialog({ detail, open, onClose }: { detail: ConversationDetail; open: boolean; onClose: () => void }) {
  const names = outfitNames(detail.state.outfit, detail.character.document);
  return (
    <Dialog title={`${detail.character.document.name}의 차림`} open={open} onClose={onClose}>
      {names.length === 0 ? (
        <p className="empty-state">처음 차림 그대로입니다. 옷을 건네면 입습니다.</p>
      ) : (
        <ul aria-label="입은 옷">
          {names.map((name, index) => (
            <li key={`${index}-${name}`}>{name}</li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
