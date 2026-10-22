// web/apps/web/src/api/errors.ts
// 서버의 실패 응답을 화면이 다룰 하나의 모양(ApiError)으로 바꾼다.
// 서버마다 오류의 본문이 조금씩 다르다: {"detail"}, {"detail","code"}, {"detail","code","retry_after"}, 칸마다의 글({"username": [...]}).

export type FieldErrors = Record<string, string[]>;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;
  readonly retryAfter: number | undefined;
  readonly fields: FieldErrors;
  readonly requestId: string | undefined;

  constructor(init: {
    status: number;
    detail: string;
    code?: string | undefined;
    retryAfter?: number | undefined;
    fields?: FieldErrors;
    requestId?: string | undefined;
  }) {
    super(init.detail);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.retryAfter = init.retryAfter;
    this.fields = init.fields ?? {};
    this.requestId = init.requestId;
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
    code: typeof body.code === 'string' ? body.code : undefined,
    retryAfter: retryAfterOf(body, response.headers),
    fields: fieldErrorsOf(body),
    requestId: response.headers.get('X-Request-ID') ?? undefined,
  });
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

/** 칸마다의 오류 글. 글의 목록인 값만 칸으로 본다(detail, code 같은 글 하나는 칸이 아니다) */
function fieldErrorsOf(body: Record<string, unknown>): FieldErrors {
  const fields: FieldErrors = {};
  for (const [name, value] of Object.entries(body)) {
    if (Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      fields[name] = value;
    }
  }
  return fields;
}
