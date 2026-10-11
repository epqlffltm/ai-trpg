// board-server/src/app.setup.ts

/**
 * 만들어진 앱에 주소의 규칙과 응답의 규칙을 건다. 서버를 띄울 때(main.ts)와 테스트가 같은 것을 쓴다.
 *
 * 따로 둔 이유: 테스트가 앱을 직접 만들기 때문이다. 규칙을 main.ts 에만 적으면 테스트의 앱에는 걸리지 않아서,
 * 테스트는 통과하는데 실제 서버의 주소는 다른 일이 생긴다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { requestLogging } from './observability/request-logging.middleware.js';

/** 이 서버의 API 가 놓이는 주소의 앞부분. 프록시가 이 앞부분으로 서버를 가른다 */
export const API_PREFIX = 'api/v1/board';

/** API 주소 밖에 두는 주소들. 프록시와 컨테이너 관리 도구가 부른다 */
const OUTSIDE_THE_API = ['health', 'health/ready'];

/**
 * 앱에 규칙을 건다.
 *
 *   - 컨트롤러의 주소를 모두 API_PREFIX 아래에 놓는다. /health 와 /health/ready 는 밖에 둔다.
 *   - 요청마다 식별자(request_id, trace_id)를 걸고, 끝나면 한 줄을 남긴다. 응답에 X-Request-ID 를 돌려준다
 *     (observability/request-logging.middleware.ts). 다른 것보다 먼저 건다. 401 과 404 에도 식별자가 붙는다.
 *   - 응답에서 X-Powered-By 머리말을 뺀다. 어떤 프레임워크로 만들었는지 알려 줄 이유가 없다.
 */
export function setupApp(app: NestExpressApplication): void {
  app.use(requestLogging());
  app.setGlobalPrefix(API_PREFIX, { exclude: OUTSIDE_THE_API });
  app.disable('x-powered-by');
}
