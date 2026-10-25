// web/apps/web/src/pages/trpg/room/round/EarlierRounds.tsx
// 최근의 라운드 위의 한 줄(B10). 아직 보이지 않는 앞의 라운드 수와 "앞의 라운드 더 보기". 한 번에 ROUND_PAGE 개씩 위에 잇는다.
// 읽지 못하면 까닭과 다시 시도. 읽은 라운드는 그대로 둔다.

import { Button } from '@ai-trpg/ui';
import { ROUND_PAGE } from '../../../../api/rounds';

type Props = { hidden: number; busy: boolean; failed: boolean; onMore: () => void };

export function EarlierRounds({ hidden, busy, failed, onMore }: Props) {
  if (hidden === 0) return null;
  return (
    <div className="earlier-rounds">
      <p className="hint">
        앞의 라운드 {hidden}개{failed ? ' · 불러오지 못했습니다' : ''}
      </p>
      <Button variant="secondary" busy={busy} onClick={onMore}>
        {failed ? '다시 시도' : `앞의 라운드 더 보기(${Math.min(hidden, ROUND_PAGE)}개)`}
      </Button>
    </div>
  );
}
