// board-server/src/openapi/export.ts

/**
 * 이 서버의 API 목록(OpenAPI)을 JSON 으로 표준 출력에 낸다. 서버를 띄우지 않고 DB 에도 닿지 않는다.
 *
 *     npm run --silent openapi      # 빌드한 뒤 이것을 돌린다(package.json)
 *
 * 저장소의 도구(tools/export_openapi.py)가 이것을 불러 docs/api/board.openapi.json 을 쓰고, CI 가 견준다.
 *
 * 앱은 미리 보기(preview)로 만든다. 모듈과 주소의 짜임만 읽고 프로바이더를 만들지 않는다.
 * 그래서 DB 에 붙지 않고, 인증 서버의 키를 받지 않고, 알림을 보내는 일도 돌지 않는다.
 * 다만 설정은 읽으므로 DATABASE_URL 과 AUTH_JWKS_URL 이 있어야 한다. 도구가 닿지 않는 주소를 채워 넘긴다.
 * Nest 의 로그는 끈다. 표준 출력에는 JSON 만 나가야 한다.
 */

import { NestFactory } from '@nestjs/core';
import { NestExpressApplication } from '@nestjs/platform-express';
import { AppModule } from '../app.module.js';
import { setupApp } from '../app.setup.js';
import { buildDocument } from './document.js';

/** 목록을 읽기 위한 앱. 주소의 규칙(setupApp)을 서버와 같게 건다. */
async function createPreviewApp(): Promise<NestExpressApplication> {
  const app = await NestFactory.create<NestExpressApplication>(AppModule, {
    preview: true,
    logger: false,
    abortOnError: false,
  });
  setupApp(app);
  return app;
}

/** 목록을 만들어 표준 출력에 쓴다. 앱은 쓰고 나서 닫는다. */
async function exportDocument(): Promise<void> {
  const app = await createPreviewApp();
  try {
    process.stdout.write(JSON.stringify(buildDocument(app)));
  } finally {
    await app.close();
  }
}

await exportDocument();
