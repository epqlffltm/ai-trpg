// web/apps/web/src/pages/trpg/room/round/outcomeReason.ts
// 결과의 못 한 까닭(서버의 reason 이름)을 괄호의 글로. 순수한 함수다. 맵의 결과(mapOutcome.ts)와 행동의 결과(actionOutcome.ts)가 함께 쓴다.

/** 까닭을 괄호로. "(열쇠가 없었습니다)". 모르는 이름이면 그대로, 없으면 빈 글 */
export function because(reasons: Record<string, string>, reason: string | null | undefined): string {
  return reason ? `(${reasons[reason] ?? reason})` : '';
}
