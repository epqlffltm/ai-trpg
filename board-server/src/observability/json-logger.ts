// board-server/src/observability/json-logger.ts

/**
 * 로그 한 줄을 공통 규격의 JSON 으로 내보내는 로거. Nest 의 로거 자리에 꽂는다(main.ts 의 app.useLogger).
 * 규격은 저장소 루트의 docs/observability.md 에 있다.
 *
 * 로그를 남기는 코드는 그대로 Nest 의 Logger 를 쓴다.
 *
 *     private readonly logger = new Logger(PostsService.name);
 *     this.logger.warn('글을 저장하지 못했다');
 *     this.logger.log({ message: '요청을 처리했다', operation: 'http.request', duration_ms: 12 });
 *
 * 여기서 그 한 줄에 시각, 수준, 서비스 이름, 환경, 버전, 지금 걸려 있는 식별자(request_id, trace_id)를 붙인다.
 * 칸을 더 싣고 싶으면 글자 대신 객체를 넘긴다. 객체의 칸은 민감한 값을 가린 뒤에 싣는다(redaction.ts).
 *
 * 한 줄에 JSON 하나다. 글 안의 줄바꿈은 JSON 이 \n 으로 바꿔 적는다. 메시지에 줄바꿈을 넣어 가짜 로그 줄을 만들 수 없다.
 */

import { LoggerService } from '@nestjs/common';
import { ContextIds, currentIds } from './request-context.js';
import {
  MAX_MESSAGE_LENGTH,
  MAX_STACK_LENGTH,
  safeValue,
  scrubText,
} from './redaction.js';

/** 규격의 수준 이름. 낮은 것부터다 */
export const LOG_LEVELS = [
  'debug',
  'info',
  'warning',
  'error',
  'critical',
] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

/** 모든 로그 줄에 붙는, 이 서버가 누구인지. */
export interface ServiceInfo {
  readonly service: string;
  readonly environment: string;
  readonly version: string;
}

/** 로그 한 줄을 내보내는 함수. 테스트가 줄을 모으는 함수로 바꿔 꽂는다 */
export type WriteLine = (line: string) => void;
/** 지금 시각을 돌려주는 함수 */
export type Now = () => Date;

/** 객체로 넘겨도 덮어쓸 수 없는 칸. 이 서버가 정하는 값이다 */
const FIXED_FIELDS = new Set([
  'timestamp',
  'level',
  'service',
  'environment',
  'version',
  'logger',
  'message',
]);
/** 예외의 기록을 싣는 칸의 이름 */
const STACK_FIELD = 'stack_trace';

/** 로그를 표준 오류(stderr)로 내보낸다. 모으는 것은 서버 밖의 일이다. */
export function writeToStderr(line: string): void {
  process.stderr.write(`${line}\n`);
}

/** level 이 threshold 이상인가. 그 수준부터 남긴다. */
export function isLevelEnabled(level: LogLevel, threshold: LogLevel): boolean {
  return LOG_LEVELS.indexOf(level) >= LOG_LEVELS.indexOf(threshold);
}

/** 값이 이름과 값의 묶음(객체)인가. 배열과 오류는 아니다. */
function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === 'object' &&
    value !== null &&
    !Array.isArray(value) &&
    !(value instanceof Error)
  );
}

/** 로그에 넘어온 것에서 메시지의 글을 꺼낸다. 객체면 그 안의 message 칸이다. */
export function messageOf(message: unknown): string {
  if (typeof message === 'string') {
    return message;
  }
  if (message instanceof Error) {
    return `${message.name}: ${message.message}`;
  }
  if (isRecord(message)) {
    return typeof message.message === 'string' ? message.message : '';
  }
  return String(message);
}

/** 객체로 넘어온 칸들. 민감한 값은 가려져 있다. 이 서버가 정하는 칸은 덮어쓰지 못한다. */
export function extraFields(message: unknown): Record<string, unknown> {
  if (!isRecord(message)) {
    return {};
  }
  const fields: Record<string, unknown> = {};
  for (const [name, value] of Object.entries(message)) {
    if (FIXED_FIELDS.has(name)) {
      continue;
    }
    // 예외의 기록은 길다. 다른 칸처럼 짧게 자르지 않는다
    fields[name] =
      name === STACK_FIELD && typeof value === 'string'
        ? scrubText(value, MAX_STACK_LENGTH)
        : safeValue(name, value);
  }
  return fields;
}

/**
 * Nest 가 메시지 뒤에 넘기는 것들에서 어디서 남긴 로그인지(context)와 예외의 기록(stack)을 가린다.
 *
 * Nest 의 Logger 는 맨 뒤에 context 를 붙여 넘긴다. error 는 그 앞에 stack 을 넘길 수 있다.
 *     logger.warn(message)          -> (message, context)
 *     logger.error(message, stack)  -> (message, stack, context)
 */
export function splitParams(params: unknown[]): {
  context?: string;
  stack?: string;
} {
  const texts = params.filter(
    (param): param is string => typeof param === 'string',
  );
  const context = texts.at(-1);
  const stack = texts.length > 1 ? texts.at(-2) : undefined;
  return { context, stack };
}

export class JsonLogger implements LoggerService {
  constructor(
    private readonly info: ServiceInfo,
    private readonly threshold: LogLevel = 'info',
    private readonly write: WriteLine = writeToStderr,
    private readonly now: Now = () => new Date(),
  ) {}

  log(message: unknown, ...params: unknown[]): void {
    this.emit('info', message, splitParams(params).context);
  }

  warn(message: unknown, ...params: unknown[]): void {
    this.emit('warning', message, splitParams(params).context);
  }

  debug(message: unknown, ...params: unknown[]): void {
    this.emit('debug', message, splitParams(params).context);
  }

  /** Nest 의 verbose 는 규격에 없다. debug 로 남긴다. */
  verbose(message: unknown, ...params: unknown[]): void {
    this.emit('debug', message, splitParams(params).context);
  }

  error(message: unknown, ...params: unknown[]): void {
    const { context, stack } = splitParams(params);
    this.emit('error', message, context, stack);
  }

  /** Nest 의 fatal 은 규격의 critical 이다. */
  fatal(message: unknown, ...params: unknown[]): void {
    const { context, stack } = splitParams(params);
    this.emit('critical', message, context, stack);
  }

  /** 로그 한 줄을 만들어 내보낸다. 남기는 수준보다 낮으면 아무것도 하지 않는다. */
  private emit(
    level: LogLevel,
    message: unknown,
    context?: string,
    stack?: string,
  ): void {
    if (!isLevelEnabled(level, this.threshold)) {
      return;
    }
    this.write(
      JSON.stringify(this.entry(level, message, context, stack, currentIds())),
    );
  }

  /**
   * 로그 한 줄의 내용을 만든다. 뒤에 오는 것이 앞의 것을 덮는다.
   * 객체로 넘어온 칸 < 예외의 기록 < 지금 걸려 있는 식별자. 식별자는 걸려 있는 것이 이긴다.
   */
  private entry(
    level: LogLevel,
    message: unknown,
    context: string | undefined,
    stack: string | undefined,
    ids: ContextIds,
  ): Record<string, unknown> {
    return {
      timestamp: this.now().toISOString(),
      level,
      service: this.info.service,
      environment: this.info.environment,
      version: this.info.version,
      logger: context,
      message: scrubText(messageOf(message), MAX_MESSAGE_LENGTH),
      ...extraFields(message),
      ...(stack === undefined
        ? {}
        : { [STACK_FIELD]: scrubText(stack, MAX_STACK_LENGTH) }),
      ...ids,
    };
  }
}
