// web/apps/web/src/api/errors.ts
// 서버의 실패 응답을 화면이 다룰 하나의 모양(ApiError)으로 바꾼다.
// 서버마다 오류의 본문이 조금씩 다르다: {"detail"}, {"detail","code"}, {"detail","reason"}(게임의 409), {"detail","code","retry_after"}, 칸마다의 글({"username": [...]}).

export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly retryAfter: number | undefined;
  readonly fields: FieldErrors;
  readonly requestId: string | undefined;
  /** 본문 그대로. 화면마다 따로 읽는 칸(지우지 못한 재료를 쓰는 시나리오의 used_by 같은 것)이 있을 때 읽는다 */
  readonly body: Record<string, unknown>;

  constructor(init: {
    status: number;
    detail: string;
    code?: string | undefined;
    retryAfter?: number | undefined;
    fields?: FieldErrors;
    requestId?: string | undefined;
    body?: Record<string, unknown>;
  }) {
    super(init.detail);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.retryAfter = init.retryAfter;
    this.fields = init.fields ?? {};
    this.requestId = init.requestId;
    this.body = init.body ?? {};
  }
}

/** 서버에 닿지 못했을 때(연결이 끊김, 주소를 찾지 못함). 상태 코드가 없다 */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('서버에 닿지 못했습니다.', { cause });
    this.name = 'NetworkError';
  }
}

const FALLBACK_DETAIL = '요청을 처리하지 못했습니다.';

/** 실패한 응답을 ApiError 로. 본문이 JSON 이 아니어도(프록시의 오류 등) 상태 코드는 남는다 */
export async function toApiError(response: Response): Promise<ApiError> {
  const body = await readJsonObject(response);
  return new ApiError({
    status: response.status,
    detail: typeof body.detail === 'string' ? body.detail : FALLBACK_DETAIL,
    code: codeOf(body),
    retryAfter: retryAfterOf(body, response.headers),
    fields: fieldErrorsOf(body),
    requestId: response.headers.get('X-Request-ID') ?? undefined,
    body,
  });
}

/** 실패의 까닭. 대개 code 이고, 게임 서버의 409 는 reason 에 싣는다(테이블의 table_full 같은 것) */
function codeOf(body: Record<string, unknown>): string | undefined {
  if (typeof body.code === 'string') return body.code;
  return typeof body.reason === 'string' ? body.reason : undefined;
}

async function readJsonObject(response: Response): Promise<Record<string, unknown>> {
  try {
    const value: unknown = await response.json();
    return value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

/** 기다릴 초. 본문의 retry_after 가 먼저고, 없으면 Retry-After 머리말 */
function retryAfterOf(body: Record<string, unknown>, headers: Headers): number | undefined {
  if (typeof body.retry_after === 'number') return body.retry_after;
  const header = Number(headers.get('Retry-After'));
  return Number.isFinite(header) && header > 0 ? header : undefined;
}

/**
 * 칸마다의 오류 글. 글의 목록(["..."])이나, 그 안에 다시 칸이 있는 것({"terms": ["..."]})을 칸으로 본다.
 * detail, code 같은 글 하나는 칸이 아니다. 안쪽 칸의 글은 바깥 칸의 글로 모은다(동의의 항목마다의 오류 같은 것)
 */
function fieldErrorsOf(body: Record<string, unknown>): FieldErrors {
  const fields: FieldErrors = {};
  for (const [name, value] of Object.entries(body)) {
    const messages = messagesIn(value);
    if (messages.length > 0 && typeof value !== 'string') fields[name] = messages;
  }
  return fields;
}

function messagesIn(value: unknown): string[] {
  if (typeof value === 'string') return [value];
  if (Array.isArray(value)) return value.flatMap(messagesIn);
  if (value !== null && typeof value === 'object') return Object.values(value).flatMap(messagesIn);
  return [];
}

/** 운영자가 막은 IP 에서 온 요청이라 인증 서버가 거절했는가(#638). 가입, 로그인, 토큰 갱신이 이것으로 답한다 */
export function isNetworkBlocked(error: ApiError): boolean {
  return error.status === 403 && error.code === 'network_blocked';
}
