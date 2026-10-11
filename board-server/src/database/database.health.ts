// board-server/src/database/database.health.ts

/**
 * DB 에 닿는지 확인한다. 준비됐는지 묻는 API(health/readiness.controller.ts)가 쓴다.
 *
 * 따로 둔 이유: 그 API 의 테스트가 "DB 에 닿지 않을 때"를 만들려면 이것 하나만 바꿔 꽂으면 된다.
 */

import { Injectable } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

@Injectable()
export class DatabaseHealth {
  constructor(@InjectDataSource() private readonly dataSource: DataSource) {}

  /** 가장 가벼운 쿼리를 보내 본다. 닿지 않으면 예외가 난다. */
  async ping(): Promise<void> {
    await this.dataSource.query('SELECT 1');
  }
}
