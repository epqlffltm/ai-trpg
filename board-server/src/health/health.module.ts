// board-server/src/health/health.module.ts

/**
 * 살아 있는지 확인하는 API 를 묶은 모듈.
 *
 * Nest 는 기능마다 모듈을 두고, 앱 모듈(app.module.ts)이 그것들을 모은다.
 * 모듈은 "이 기능에 어떤 컨트롤러와 서비스가 있는가"를 적은 목록이다.
 */

import { Module } from '@nestjs/common';
import { HealthController } from './health.controller.js';

@Module({
  controllers: [HealthController],
})
export class HealthModule {}
