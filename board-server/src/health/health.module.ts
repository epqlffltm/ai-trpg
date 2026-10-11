// board-server/src/health/health.module.ts

/**
 * 살아 있는지, 준비됐는지 확인하는 API 를 묶은 모듈.
 *
 * Nest 는 기능마다 모듈을 두고, 앱 모듈(app.module.ts)이 그것들을 모은다.
 * 모듈은 "이 기능에 어떤 컨트롤러와 서비스가 있는가"를 적은 목록이다.
 * 다른 모듈의 것을 쓰려면 그 모듈을 imports 에 적는다. 준비됐는지 묻는 API 가 DB 모듈의 DatabaseHealth 를 쓴다.
 */

import { Module } from '@nestjs/common';
import { DatabaseModule } from '../database/database.module.js';
import { HealthController } from './health.controller.js';
import { ReadinessController } from './readiness.controller.js';

@Module({
  imports: [DatabaseModule],
  controllers: [HealthController, ReadinessController],
})
export class HealthModule {}
