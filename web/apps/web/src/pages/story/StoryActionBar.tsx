// web/apps/web/src/pages/story/StoryActionBar.tsx
// 장면(D2)의 행동 단추 줄(Stitch 22번의 왼쪽 열, 창 아래에 띄운 줄). 시간 보내기, 하루 마치기(기한의 마지막 날이면 한 번 더 묻는다),
// 책갈피와 그림으로 저장(#982). 지도·소지품·기록·기억은 왼쪽 열의 창(StoryTools)이다.
// 행동은 엔진이 판정하고 반응을 받는다(청구 한 번). 받는 중이거나 끝난 세션이면 막는다.

import { Button } from '@ai-trpg/ui';
import type { StoryAction, StoryState, StoryView } from '../../api/story';
import { ConfirmButton } from '../../components/ConfirmButton';
import { canPassTime, isLastDay } from './storyActions';
import type { ReactNode } from 'react';

type Props = {
  view: StoryView;
  state: StoryState;
  disabled: boolean;
  onAct: (action: StoryAction) => Promise<boolean>;
  /** 책갈피와 그림으로 저장의 단추(장면이 들고 있다) */
  tools: ReactNode;
};

export function StoryActionBar({ view, state, disabled, onAct, tools }: Props) {
  const timeFlows = canPassTime(view, state);
  return (
    <div className="story-actions" role="toolbar" aria-label="행동">
      {timeFlows ? (
        <>
          <Button variant="secondary" disabled={disabled} onClick={() => void onAct({ kind: 'pass_time' })}>
            시간 보내기
          </Button>
          <EndDayButton lastDay={isLastDay(view, state)} disabled={disabled} onAct={onAct} />
        </>
      ) : null}
      {tools}
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
