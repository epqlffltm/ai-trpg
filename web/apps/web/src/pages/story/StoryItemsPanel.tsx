// web/apps/web/src/pages/story/StoryItemsPanel.tsx
// 소지품·건네기(D4, Stitch 22번의 왼쪽 열 창). 가진 물건과 수, 설명. 건네기는 장면의 인물을 눌러 한다(인물 메뉴, StoryCastRow).

import type { StoryState, StoryView } from '../../api/story';
import { heldItems } from './storyActions';

export function StoryItemsPanel({ view, state }: { view: StoryView; state: StoryState }) {
  const items = heldItems(view, state.items);
  return (
    <>
      {items.length === 0 ? <p className="empty-state">가진 물건이 없습니다.</p> : null}
      <ul className="plain-list story-items" aria-label="가진 물건">
        {items.map((item) => (
          <li key={item.id}>
            <strong>{item.name}</strong> × {item.count}
            {item.description ? <p className="hint">{item.description}</p> : null}
          </li>
        ))}
      </ul>
      <p className="hint">건네기는 장면의 인물을 눌러 합니다.</p>
    </>
  );
}
