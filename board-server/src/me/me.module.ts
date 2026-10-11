// board-server/src/me/me.module.ts

/**
 * 토큰의 주인을 돌려주는 API 를 묶은 모듈.
 */

import { Module } from '@nestjs/common';
import { MeController } from './me.controller.js';

@Module({
  controllers: [MeController],
})
export class MeModule {}
