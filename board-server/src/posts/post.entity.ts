// board-server/src/posts/post.entity.ts

/**
 * 글 하나. posts 테이블의 모양이다.
 *
 *   - id 는 순번이다(bigint). 번호의 차례가 곧 쓴 차례다. 글 목록은 번호가 큰 것부터 보여 준다.
 *     JavaScript 의 숫자는 큰 정수를 정확히 담지 못해서, 코드와 응답에서는 글자로 다룬다.
 *   - 글쓴이는 인증 서버의 public_id 로만 가리킨다. 이름은 이 테이블에 없다.
 *     글쓴이가 탈퇴하면 비운다(null, withdrawals/). 글은 남고 "탈퇴한 사용자"의 글로 보인다.
 *   - 지운 글은 행을 없애지 않고 지운 시각을 적는다(deleted_at). 읽는 쿼리는 지운 글을 알아서 뺀다.
 *     행을 없애면 나중에 붙을 댓글과 신고의 기록이 가리킬 곳을 잃는다.
 *   - 고정한 글은 고정한 시각(pinned_at)과 고정이 끝나는 시각(pinned_until)을 적는다. 둘은 함께 있거나 함께 없다.
 *     끝나는 시각이 지나면 고정이 풀린 것으로 읽는다. 열을 비우는 작업을 따로 돌리지 않는다(pins.policy.ts).
 *   - 제목과 본문은 받은 글자를 그대로 저장한다. 서버는 HTML 로 해석하지 않는다. 화면에 그릴 때 글자로 그린다.
 */

import {
  Check,
  Column,
  CreateDateColumn,
  DeleteDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  UpdateDateColumn,
} from 'typeorm';
import { Board } from '../boards/board.entity.js';

/** 제목의 최대 길이(글자) */
export const TITLE_MAX_LENGTH = 100;
/** 본문의 최대 길이(글자) */
export const CONTENT_MAX_LENGTH = 20000;

@Entity('posts')
// 한 사람이 최근에 쓴 글을 센다. 쓰기 횟수 제한이 이 색인을 탄다(write-limits/)
@Index('ix_posts_author_id_created_at', ['authorId', 'createdAt'])
// 고정한 시각과 끝나는 시각은 함께 있거나 함께 없다. 하나만 있는 행은 고정인지 아닌지 알 수 없다
@Check('ck_posts_pin_pair', '("pinned_at" IS NULL) = ("pinned_until" IS NULL)')
// 한 게시판의 글을 번호가 큰 것부터 읽는다. 글 목록이 이 색인을 탄다
@Index('ix_posts_board_id_id', ['boardId', 'id'])
// 한 게시판의 지금 고정되어 있는 글을 읽고 센다(pinned_until > 지금).
// 고정한 적이 있는 글만 담는 색인이라 작다. 글의 대부분은 고정하지 않은 글이다
@Index('ix_posts_board_id_pinned_until', ['boardId', 'pinnedUntil'], {
  where: '"pinned_until" IS NOT NULL',
})
export class Post {
  @PrimaryGeneratedColumn('identity', {
    type: 'bigint',
    generatedIdentity: 'ALWAYS',
    primaryKeyConstraintName: 'pk_posts',
  })
  id: string;

  @Column({ name: 'board_id', type: 'integer' })
  boardId: number;

  /** 글이 있는 게시판은 지울 수 없다(RESTRICT) */
  @ManyToOne(() => Board, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'board_id', foreignKeyConstraintName: 'fk_posts_board' })
  board: Board;

  /** 글쓴이. 인증 서버의 public_id. 탈퇴한 사람이면 null 이다 */
  @Column({ name: 'author_id', type: 'uuid', nullable: true })
  authorId: string | null;

  @Column({ type: 'varchar', length: TITLE_MAX_LENGTH })
  title: string;

  @Column({ type: 'text' })
  content: string;

  /** 고정한 시각. 고정한 적이 없거나 풀었으면 null 이다. 고정한 글끼리는 나중에 고정한 것이 위에 온다 */
  @Column({ name: 'pinned_at', type: 'timestamptz', nullable: true })
  pinnedAt: Date | null;

  /** 고정이 끝나는 시각. 이 시각이 지나면 고정이 풀린 것으로 읽는다 */
  @Column({ name: 'pinned_until', type: 'timestamptz', nullable: true })
  pinnedUntil: Date | null;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  /** 마지막으로 고친 시각. 고친 적이 없으면 쓴 시각과 같다 */
  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;

  /** 지운 시각. 지우지 않았으면 null 이다 */
  @DeleteDateColumn({ name: 'deleted_at', type: 'timestamptz' })
  deletedAt: Date | null;
}
