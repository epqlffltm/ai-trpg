// board-server/src/openapi/audience.ts

/**
 * API 목록(docs/api/board.openapi.json)에 누가 부르는 API 인지를 적는 표시.
 *
 * 목록을 모으는 도구(tools/export_openapi.py)는 주소의 모양으로 누가 부르는지를 정한다. /admin/ 이 든 주소면 운영자다.
 * 이 서버의 운영자 API(신고 처리, 글 고정)는 주소에 /admin/ 이 없다. 주소로는 알 수 없어서 서버가 직접 적는다.
 * 도구는 서버가 적은 표시를 덮어쓰지 않는다. 화면은 이 표시로 일반 화면과 관리자 화면이 부를 API 를 가른다.
 *
 * 표시는 목록에만 쓰인다. 운영자만 부르게 막는 것은 서비스가 한다(pins.service.ts, report-reviews.service.ts).
 */

import { ApiExtension } from '@nestjs/swagger';

/** 누가 부르는지를 적는 칸의 이름. tools/export_openapi.py 와 같다 */
export const AUDIENCE_EXTENSION = 'x-audience';

/** 운영자의 값. tools/export_openapi.py 의 AUDIENCE_RULES 와 같다 */
export const OPERATOR_AUDIENCE = 'operator';

/** 운영자가 부르는 API 라는 표시. 컨트롤러에 붙이면 그 안의 API 가 모두 운영자의 것이다. */
export const ForOperators = () =>
  ApiExtension(AUDIENCE_EXTENSION, OPERATOR_AUDIENCE);
