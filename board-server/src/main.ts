// board-server/src/main.ts

/**
 * 서버를 띄우는 시작점. 앱을 만들고, 규칙을 걸고(app.setup.ts), 설정에 적힌 주소와 포트에서 요청을 받는다.
 *
 * 설정이 틀리면 앱을 만드는 데서(NestFactory.create) 예외가 나고 요청을 받기 전에 프로세스가 끝난다.
 *
 * 로그는 공통 규격의 JSON 으로 내보낸다(observability/json-logger.ts). Nest 의 로거 자리에 꽂는다.
 * 그래서 이 서버의 코드든 Nest 든, Nest 의 Logger 로 남긴 것은 모두 같은 모양으로 나간다.
 */

import { NestFactory } from '@nestjs/core';
import { ConfigService } from '@nestjs/config';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module.js';
import { setupApp } from './app.setup.js';
import { Environment } from './config/environment.js';
import { createLogger } from './observability/logger.factory.js';

async function bootstrap(): Promise<void> {
  // 로거를 꽂기 전에 남은 로그는 모아 두었다가(bufferLogs) 꽂은 뒤에 내보낸다.
  // 로거를 만들려면 설정이 필요하고, 설정은 앱이 만들어져야 읽힌다
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    bufferLogs: true,
  });
  const config = app.get<ConfigService<Environment, true>>(ConfigService);
  app.useLogger(createLogger(config));
  setupApp(app);
  await app.listen(
    config.get('PORT', { infer: true }),
    config.get('HOST', { infer: true }),
  );
}
await bootstrap();
