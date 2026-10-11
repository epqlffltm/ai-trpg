// board-server/src/operators/operators.service.ts

/**
 * 누가 운영자인지 답한다.
 *
 * "이 사람이 운영자인가"는 이 함수 하나로만 묻는다. 지금은 operators 테이블을 본다.
 * 나중에 인증 서버가 토큰에 역할을 실어 주면 이 함수만 고친다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Operator } from './operator.entity.js';

@Injectable()
export class OperatorsService {
  constructor(
    @InjectRepository(Operator)
    private readonly operators: Repository<Operator>,
  ) {}

  /** 이 사용자가 운영자인가. userId 는 인증 서버의 public_id 다. */
  isOperator(userId: string): Promise<boolean> {
    return this.operators.existsBy({ userId });
  }
}
