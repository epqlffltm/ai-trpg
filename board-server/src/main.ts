// board-server/src/main.ts

/**
 * 서버를 띄우는 시작점. 앱을 만들고, 규칙을 걸고(app.setup.ts), 설정에 적힌 주소와 포트에서 요청을 받는다.
 *
 * 설정이 틀리면 앱을 만드는 데서(NestFactory.create) 예외가 나고 요청을 받기 전에 프로세스가 끝난다.
 */

import { NestFactory } from '@nestjs/core';
import { ConfigService } from '@nestjs/config';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from './app.module.js';
import { setupApp } from './app.setup.js';
import { Environment } from './config/environment.js';

async function bootstrap(): Promise<void> {
  const app = await NestFactory.create<NestExpressApplication>(AppModule);
  setupApp(app);
  const config = app.get<ConfigService<Environment, true>>(ConfigService);
  await app.listen(
    config.get('PORT', { infer: true }),
    config.get('HOST', { infer: true }),
  );
}
await bootstrap();
