// board-server/src/boards/board.entity.ts

/**
 * 게시판 하나. boards 테이블의 모양이다.
 *
 * 게시판은 코드가 아니라 데이터로 둔다. 어떤 게시판이 있는지는 마이그레이션이 넣는다(migrations 의 SeedBoards).
 * 게시판을 더하려면 마이그레이션으로 행을 더한다. 운영자가 화면에서 만드는 API 는 없다.
 *
 * 테이블과 제약의 이름을 직접 적는다. TypeORM 이 지어 주는 이름(PK_8c82d7...)은 읽을 수 없다.
 */

import {
  Check,
  Column,
  CreateDateColumn,
  Entity,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';

/** 이 게시판에 누가 글을 쓸 수 있는가. member 는 로그인한 누구나, operator 는 운영자만이다 */
export const WRITE_POLICIES = ['member', 'operator'] as const;
export type WritePolicy = (typeof WRITE_POLICIES)[number];

@Entity('boards')
@Unique('uq_boards_slug', ['slug'])
// 코드가 모르는 값이 DB 에 들어오지 못하게 한다. WRITE_POLICIES 와 같아야 한다
@Check('ck_boards_write_policy', `"write_policy" IN ('member', 'operator')`)
export class Board {
  @PrimaryGeneratedColumn('identity', {
    type: 'integer',
    generatedIdentity: 'ALWAYS',
    primaryKeyConstraintName: 'pk_boards',
  })
  id: number;

  /** 주소에 쓰는 이름. 영문 소문자와 숫자, 붙임표만 쓴다(예: notice). 바꾸면 주소가 깨지므로 바꾸지 않는다 */
  @Column({ type: 'varchar', length: 30 })
  slug: string;

  /** 화면에 보이는 이름(예: 공지사항) */
  @Column({ type: 'varchar', length: 50 })
  name: string;

  /** 게시판을 한 줄로 소개하는 글 */
  @Column({ type: 'varchar', length: 200 })
  description: string;

  /** 이 게시판에 누가 글을 쓸 수 있는가 */
  @Column({ name: 'write_policy', type: 'varchar', length: 20 })
  writePolicy: WritePolicy;

  /** 게시판 목록에서의 차례. 작은 것이 먼저다 */
  @Column({ type: 'integer' })
  position: number;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;
}
