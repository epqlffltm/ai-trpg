// web/apps/web/src/pages/story/StoryActionBar.tsx
// 장면(D2)의 행동 단추 줄. 시간 보내기, 하루 마치기(기한의 마지막 날이면 한 번 더 묻는다), 지도(이동, D3), 소지품(D4), 기록(엔딩과 이벤트, D6).
// 행동은 엔진이 판정하고 반응을 받는다(청구 한 번). 받는 중이거나 끝난 세션이면 막는다.
// 건네기는 인물 메뉴(StoryCastRow)에서 한다. 소지품 창은 가진 것을 보이기만 한다.

import { Button, Dialog } from '@ai-trpg/ui';
import { useCallback, useState } from 'react';
import type { StoryAction, StoryState, StoryView } from '../../api/story';
import { ConfirmButton } from '../../components/ConfirmButton';
import { canPassTime, heldItems, isLastDay } from './storyActions';
import { StoryMapButton } from './StoryMapButton';
import { StoryRecordsButton } from './StoryRecordsButton';

type Props = { worldId: string; view: StoryView; state: StoryState; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> };

export function StoryActionBar({ worldId, view, state, disabled, onAct }: Props) {
  const timeFlows = canPassTime(view, state);
  return (
    <div className="story-actions" role="toolbar" aria-label="행동">
      {timeFlows ? (
        <>
          <Button variant="secondary" disabled={disabled} onClick={() => void onAct({ kind: 'pass_time' })}>
            시간 보내기
          </Button>
          <EndDayButton lastDay={isLastDay(view, state)} disabled={disabled} onAct={onAct} />
          <StoryMapButton view={view} state={state} disabled={disabled} onAct={onAct} />
        </>
      ) : null}
      <ItemsButton view={view} state={state} />
      <StoryRecordsButton worldId={worldId} view={view} />
    </div>
  );
}

function EndDayButton({ lastDay, disabled, onAct }: { lastDay: boolean; disabled: boolean; onAct: (action: StoryAction) => Promise<boolean> }) {
  if (!lastDay || disabled) {
    return (
      <Button variant="secondary" disabled={disabled} onClick={() => void onAct({ kind: 'end_day' })}>
        하루 마치기
      </Button>
    );
  }
  return (
    <ConfirmButton
      label="하루 마치기"
      title="마지막 날을 마칩니다"
      confirm="하루 마치기"
      busy={false}
      problem={undefined}
      variant="secondary"
      onConfirm={async () => {
        void onAct({ kind: 'end_day' });
        return true;
      }}
    >
      <p>기한의 마지막 날입니다. 하루를 마치면 기한의 엔딩이 열립니다.</p>
    </ConfirmButton>
  );
}

function ItemsButton({ view, state }: { view: StoryView; state: StoryState }) {
  const [open, setOpen] = useState(false);
  const close = useCallback(() => setOpen(false), []);
  const items = heldItems(view, state.items);
  return (
    <>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        소지품
      </Button>
      <Dialog title="소지품" open={open} onClose={close}>
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
      </Dialog>
    </>
  );
}
