// web/apps/web/src/pages/me/shortcuts/shortcutsProblem.ts
// 내 단축어 저장의 실패를 보일 것으로 바꾼다. 순수한 함수다.
// asset 서버(asset-server/app/shortcuts/router.py)는 같은 이름, 20개 넘음, 길이 넘음을 422 로 막는다.
// 화면이 먼저 검사하므로 422 는 서버의 규칙이 바뀌었을 때만 온다.

import { ApiError } from '../../../api/errors';
import { commonProblem, unknownProblem, type FormProblem } from '../../../auth/problem';

const FAILED = '저장하지 못했습니다. 잠시 뒤에 다시 시도하세요.';
const REFUSED = '서버가 받지 않는 단축어가 있습니다. 이름이 겹치는지, 길이를 넘지 않는지 확인해 주세요.';

export function describeShortcutsProblem(error: unknown): FormProblem {
  const common = commonProblem(error);
  if (common || !(error instanceof ApiError)) return common ?? { message: FAILED };
  if (error.status === 422) return { message: REFUSED };
  return unknownProblem(error, FAILED);
}
