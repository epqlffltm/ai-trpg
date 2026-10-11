// board-server/src/config/environment.ts

/**
 * 환경 변수를 검사해서 이 서버의 설정으로 바꾼다. Nest 도 .env 도 모르는 순수한 함수들이다.
 *
 * 서버가 뜰 때 한 번 불린다(app.module.ts 의 ConfigModule 이 validate 로 부른다).
 * 값이 틀리면 예외를 낸다. 서버는 뜨지 않는다. 틀린 설정으로 떠서 요청을 받다가 실패하는 것보다 낫다.
 *
 * 돌려주는 값에는 타입이 붙어 있다. 꺼내 쓰는 쪽은 ConfigService<Environment, true> 로 받는다.
 * 그러면 없는 이름을 꺼내는 것을 컴파일러가 잡고, PORT 가 글자가 아니라 숫자로 나온다.
 */

/** 적지 않았을 때 듣는 주소. 이 컴퓨터 안에서만 닿는다. 컨테이너에서는 0.0.0.0 으로 바꾼다 */
export const DEFAULT_HOST = '127.0.0.1';
/** 적지 않았을 때 듣는 포트. 인증 서버가 8000, 게임 서버가 8001 을 쓴다 */
export const DEFAULT_PORT = 8002;

/** 포트로 쓸 수 있는 가장 큰 번호 */
const MAX_PORT = 65535;

/** 이 서버의 설정. 이름은 환경 변수의 이름 그대로다. */
export interface Environment {
  HOST: string;
  PORT: number;
}

/** 값이 적혀 있는가. 없거나 빈 글자면 적지 않은 것으로 본다. */
function isSet(value: unknown): value is string {
  return typeof value === 'string' && value.trim() !== '';
}

/** 듣는 주소를 읽는다. 적지 않았으면 기본값이다. */
export function readHost(value: unknown): string {
  return isSet(value) ? value.trim() : DEFAULT_HOST;
}

/**
 * 포트를 읽는다. 적지 않았으면 기본값이다.
 *
 * 숫자로만 된 글자여야 하고 1 부터 65535 사이여야 한다. 아니면 예외를 낸다.
 * "80a" 나 "8e3" 같은 글자를 숫자로 너그럽게 읽지 않는다.
 */
export function readPort(value: unknown): number {
  if (!isSet(value)) {
    return DEFAULT_PORT;
  }
  const text = value.trim();
  const port = Number(text);
  if (!/^\d+$/.test(text) || port < 1 || port > MAX_PORT) {
    throw new Error(`PORT 는 1 부터 ${MAX_PORT} 사이의 숫자여야 합니다.`);
  }
  return port;
}

/**
 * 환경 변수 전체를 받아 이 서버의 설정을 돌려준다. 틀린 값이 있으면 예외를 낸다.
 *
 * 예외의 글에 값을 싣지 않는다. 나중에 DB 주소 같은 비밀값이 설정에 들어온다.
 */
export function readEnvironment(
  variables: Record<string, unknown>,
): Environment {
  return {
    HOST: readHost(variables.HOST),
    PORT: readPort(variables.PORT),
  };
}
