// board-server/src/auth/session-revocations.refresher.ts

/**
 * 끊긴 세션의 목록을 요청과 따로, 정해 둔 간격마다 받는다(#274). 앱이 뜨면 바로 한 번 받고, 닫힐 때 멈춘다.
 *
 * 받는 일 자체는 RevocationCache 가 한다. 여기는 언제 받을지만 정한다.
 * 타이머는 프로세스를 붙잡지 않는다(unref). 이것 때문에 서버가 꺼지지 않는 일이 없다.
 */

import {
  Injectable,
  Logger,
  OnApplicationBootstrap,
  OnModuleDestroy,
} from '@nestjs/common';
import {
  FETCH_OPERATION,
  REFRESH_INTERVAL_SECONDS,
  RevocationCache,
} from './session-revocations.js';

@Injectable()
export class RevocationsRefresher
  implements OnApplicationBootstrap, OnModuleDestroy
{
  private readonly logger = new Logger(RevocationsRefresher.name);
  private timer: NodeJS.Timeout | undefined;

  constructor(private readonly cache: RevocationCache) {}

  /** 앱이 뜨면 바로 한 번 받고, 간격마다 다시 받는다. 처음 받는 것을 기다리지 않는다. 인증 서버가 꺼져 있어도 이 서버는 뜬다. */
  onApplicationBootstrap(): void {
    this.refreshInBackground();
    this.timer = setInterval(
      () => this.refreshInBackground(),
      REFRESH_INTERVAL_SECONDS * 1000,
    );
    this.timer.unref();
  }

  /** 앱이 닫힐 때 멈춘다. */
  onModuleDestroy(): void {
    clearInterval(this.timer);
    this.timer = undefined;
  }

  /**
   * 한 번 받는다. 기다리지 않는다. 받지 못한 것은 RevocationCache 가 남긴다.
   * 그 밖의 예외(코드의 버그)도 타이머를 멈추게 두지 않는다. 오류로 남기고 다음 바퀴에 다시 받는다.
   */
  private refreshInBackground(): void {
    this.cache.refresh().catch((error: unknown) => {
      this.logger.error(
        {
          message: '끊긴 세션의 목록을 받다 예상하지 못한 오류가 났다',
          operation: FETCH_OPERATION,
          error_code: 'internal.error',
          error_type:
            error instanceof Error ? error.constructor.name : typeof error,
        },
        error instanceof Error ? error.stack : undefined,
      );
    });
  }
}
