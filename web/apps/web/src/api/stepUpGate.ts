// web/apps/web/src/api/stepUpGate.ts
// 민감한 작업이 본인 확인을 요구하면(403) 확인을 받고 한 번 다시 보낸다(F5).
//
//   - 결제 서버는 창이 닫혔으면 403 step_up.required, 인증 서버는 (확인 끄기에서) 403 step_up_required 로 답한다
//   - 확인 창(대화창)은 화면의 틀이 하나 띄운다(StepUpHost). 여기는 그 창을 띄워 달라고 부탁만 한다(askStepUp)
//   - 여러 작업이 한꺼번에 요구해도 창은 하나다. 같은 결과를 함께 기다린다
//   - 확인하지 않고 닫으면 처음의 403 을 그대로 던진다. 화면이 까닭을 보인다
//   - 다시 보내도 같은 작업이 두 번 되지 않는다. 결제 서버는 확인을 묻고 나서야 작업을 시작한다(청약철회도 한 번만 취소된다)

import { ApiError } from './errors';

/** 확인 창을 띄우고 확인했으면 true, 닫았으면 false */
export type StepUpAsker = () => Promise<boolean>;

const REQUIRED_CODES = new Set(['step_up.required', 'step_up_required']);

let asker: StepUpAsker | null = null;
let pending: Promise<boolean> | null = null;

/** 확인 창을 띄울 것을 둔다. 치우는 함수를 돌려준다. 틀이 하나만 둔다 */
export function setStepUpAsker(next: StepUpAsker): () => void {
  asker = next;
  return () => {
    if (asker === next) asker = null;
  };
}

/** 확인을 받는다. 이미 창이 떠 있으면 그 결과를 함께 기다린다. 띄울 것이 없으면 false */
export function askStepUp(): Promise<boolean> {
  if (asker === null) return Promise.resolve(false);
  pending ??= asker().finally(() => {
    pending = null;
  });
  return pending;
}

/** 본인 확인이 필요하다는 답인가 */
export function isStepUpRequired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403 && error.code !== undefined && REQUIRED_CODES.has(error.code);
}

/** 부르고, 본인 확인이 필요하다는 답이면 확인을 받은 뒤 한 번 다시 부른다 */
export async function withStepUp<T>(call: () => Promise<T>): Promise<T> {
  try {
    return await call();
  } catch (error) {
    if (!isStepUpRequired(error)) throw error;
    if (!(await askStepUp())) throw error;
    return call();
  }
}
