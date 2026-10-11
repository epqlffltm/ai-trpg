// board-server/src/operators/operators.module.ts

/**
 * 운영자를 맡는 모듈. API 는 없다. 다른 모듈이 OperatorsService 로 운영자인지 묻는다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Operator } from './operator.entity.js';
import { OperatorsService } from './operators.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Operator])],
  providers: [OperatorsService],
  exports: [OperatorsService],
})
export class OperatorsModule {}
