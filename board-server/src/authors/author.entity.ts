// board-server/src/authors/author.entity.ts

/**
 * 글쓴이의 닉네임. authors 테이블의 모양이다. 사람마다 한 줄이다.
 *
 * 닉네임은 인증 서버의 것이다. 이 서버는 access 토큰에 실려 온 이름을 적어 두고 글과 댓글의 응답에 싣는다.
 * 글과 댓글의 행에는 이름을 적지 않는다. 사람의 번호만 가리킨다. 그래서 이 줄 하나를 고치면 그 사람이 쓴 글 모두에 새 이름이 나온다.
 * 글과 댓글은 이 테이블을 외래 키로 가리키지 않는다. 이름을 모르는 사람(이 기능 전에 쓴 사람)의 글도 있다.
 */

import { Column, Entity, PrimaryColumn } from 'typeorm';
import { NICKNAME_MAX_LENGTH } from './nickname.js';

@Entity('authors')
export class Author {
  /** 인증 서버의 public_id */
  @PrimaryColumn({
    name: 'user_id',
    type: 'uuid',
    primaryKeyConstraintName: 'pk_authors',
  })
  userId: string;

  @Column({ type: 'varchar', length: NICKNAME_MAX_LENGTH })
  nickname: string;

  /** 이름을 마지막으로 바꿔 적은 시각 */
  @Column({ name: 'updated_at', type: 'timestamptz', default: () => 'now()' })
  updatedAt: Date;
}
