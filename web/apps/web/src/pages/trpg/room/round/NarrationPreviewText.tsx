// web/apps/web/src/pages/trpg/room/round/NarrationPreviewText.tsx
// 결과를 서술하는 중의 글. 모델이 쓰는 글을 미리 보인다(narration_preview). 남는 글이 아니다.
// 다 쓰이면 다음 라운드의 장면으로 바뀐다. 조각을 놓쳤으면 그때까지의 글만 두고 끝나기를 기다린다.

import type { Round } from '../../../../api/types';
import type { NarrationPreview } from './preview';

export function NarrationPreviewText({ round, preview }: { round: Round; preview: NarrationPreview | null }) {
  const mine = preview && preview.round === round.number ? preview : null;
  if (round.narration_failed_at) {
    return (
      <p className="hint" role="status">
        서술에 실패했습니다({round.narration_failures}번). 방장이 다시 맡길 수 있습니다.
      </p>
    );
  }
  return (
    <div className="narration-preview" aria-live="polite">
      <p className="hint">결과를 서술하는 중입니다. 쓰이는 글은 미리 보기이며, 다 쓰이면 바뀔 수 있습니다.</p>
      {mine?.text ? <p className="prose narration-preview__text">{mine.text}</p> : null}
      {mine?.stalled ? <p className="hint">이어지는 글은 다 쓰이면 보입니다.</p> : null}
    </div>
  );
}
