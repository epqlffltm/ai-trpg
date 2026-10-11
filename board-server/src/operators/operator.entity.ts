// board-server/src/operators/operator.entity.ts

/**
 * 운영자 한 사람. operators 테이블의 모양이다.
 *
 * 인증 서버의 토큰에는 역할이 없다. 누가 게시판의 운영자인지는 이 서버가 안다.
 * 행이 있으면 운영자다. 넣고 빼는 API 는 없다. DB 에서 직접 넣는다(README 의 "운영자").
 */

import { CreateDateColumn, Entity, PrimaryColumn } from 'typeorm';

@Entity('operators')
export class Operator {
  /** 인증 서버의 public_id */
  @PrimaryColumn({
    name: 'user_id',
    type: 'uuid',
    primaryKeyConstraintName: 'pk_operators',
  })
  userId: string;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;
}
