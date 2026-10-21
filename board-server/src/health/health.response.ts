// board-server/src/health/health.response.ts

/**
 * 상태 확인 API 의 답의 모양들(health.controller.ts, readiness.controller.ts).
 *
 * 컨트롤러와 따로 둔 이유: API 목록(docs/api/board.openapi.json)은 *.response.ts 의 클래스에서 응답의 칸을 읽는다(nest-cli.json).
 */

/** 살아 있다는 답. */
export class HealthResponse {
  status: 'ok';
}

/** 준비됐는지의 답. 준비되지 않았으면 상태 코드 503 과 함께 unavailable 이다 */
export class ReadinessResponse {
  status: 'ok' | 'unavailable';
}
