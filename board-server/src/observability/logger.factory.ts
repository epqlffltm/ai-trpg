// board-server/src/observability/logger.factory.ts

/**
 * 설정에서 이 서버의 로거를 만든다. 서버를 띄울 때 한 번 부른다(main.ts).
 */

import { ConfigService } from '@nestjs/config';
import { Environment } from '../config/environment.js';
import {
  JsonLogger,
  ServiceInfo,
  WriteLine,
  writeToStderr,
} from './json-logger.js';

/** 이 서버의 이름. 로그의 service 칸에 들어간다. 규격(저장소 루트의 docs/observability.md)에 적힌 이름이다 */
export const SERVICE_NAME = 'board-server';

/** 설정에서 이 서버가 누구인지를 꺼낸다. 로그의 칸과 span 의 출처(tracing.ts)가 같은 값을 쓴다. */
export function serviceInfo(
  config: ConfigService<Environment, true>,
): ServiceInfo {
  return {
    service: SERVICE_NAME,
    environment: config.get('APP_ENVIRONMENT', { infer: true }),
    version: config.get('APP_VERSION', { infer: true }),
  };
}

/**
 * 공통 규격의 JSON 으로 내보내는 로거를 만든다. 환경의 이름, 버전, 남기는 수준을 설정에서 읽는다.
 *
 * 설정의 다른 값은 읽지 않고 적지도 않는다. 설정에는 DB 주소가 들어 있다.
 */
export function createLogger(
  config: ConfigService<Environment, true>,
  write: WriteLine = writeToStderr,
): JsonLogger {
  return new JsonLogger(
    serviceInfo(config),
    config.get('LOG_LEVEL', { infer: true }),
    write,
  );
}
