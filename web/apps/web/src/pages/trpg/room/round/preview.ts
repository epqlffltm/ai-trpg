// web/apps/web/src/pages/trpg/room/round/preview.ts
// 서술의 미리 보기(narration_preview)를 잇는다. 순수한 함수다. 규칙은 trpg-server README 의 "서술의 미리 보기".
//   - 같은 라운드, 같은 시도의 조각을 seq 차례로 이어 붙인다
//   - attempt 가 커지면(다시 시도, 다음 모델) 보던 글을 지우고 새로 받는다. 더 작은 attempt 와 지난 라운드는 버린다
//   - seq 가 비면(놓쳤거나 도중에 붙었다) 그 시도는 더 잇지 않는다(stalled). 끝나면 이벤트로 전부를 본다
//   - gm_narration, narration_failed 같은 이벤트가 오면 지운다(ENDS_PREVIEW). 남는 장면은 이벤트의 글뿐이다

import type { PreviewChunk } from '../streamPolicy';

export type NarrationPreview = {
  round: number;
  attempt: number;
  /** 다음에 이을 조각의 번호 */
  nextSeq: number;
  text: string;
  /** 조각을 놓쳐 더 잇지 않는다 */
  stalled: boolean;
};

/** 이 이벤트가 오면 미리 보기를 지운다. 서버는 마지막 조각을 보낸 뒤에 이 이벤트를 적는다 */
export const ENDS_PREVIEW: ReadonlySet<string> = new Set([
  'gm_narration',
  'narration_failed',
  'narration_abandoned',
  'round_opened',
  'table_ended',
]);

export function applyPreview(current: NarrationPreview | null, chunk: PreviewChunk): NarrationPreview | null {
  if (current && isOlder(chunk, current)) return current;
  if (!current || chunk.round !== current.round || chunk.attempt !== current.attempt) return startPreview(chunk);
  if (current.stalled || chunk.seq < current.nextSeq) return current;
  if (chunk.seq > current.nextSeq) return { ...current, stalled: true };
  return { ...current, text: current.text + chunk.text, nextSeq: current.nextSeq + 1 };
}

function isOlder(chunk: PreviewChunk, current: NarrationPreview): boolean {
  return chunk.round < current.round || (chunk.round === current.round && chunk.attempt < current.attempt);
}

/** 새 시도의 첫 조각. 첫 조각(0)이 아니면 도중에 붙은 것이라 잇지 않는다 */
function startPreview(chunk: PreviewChunk): NarrationPreview {
  const fromStart = chunk.seq === 0;
  return {
    round: chunk.round,
    attempt: chunk.attempt,
    nextSeq: fromStart ? 1 : chunk.seq + 1,
    text: fromStart ? chunk.text : '',
    stalled: !fromStart,
  };
}
