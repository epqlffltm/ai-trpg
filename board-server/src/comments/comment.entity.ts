// board-server/src/comments/comment.entity.ts

/**
 * 댓글 하나. comments 테이블의 모양이다. 댓글과 답글(대댓글)을 한 테이블에 둔다.
 *
 *   - parent_id 가 비어 있으면 글에 단 댓글이고, 있으면 그 댓글에 단 답글이다.
 *     답글에는 답글을 달지 못한다. 깊이는 두 단까지다(comments.service.ts 가 지킨다).
 *   - 번호는 순번이다(bigint). 번호의 차례가 곧 쓴 차례다. 댓글은 번호가 작은 것(먼저 쓴 것)부터 보여 준다.
 *   - 글쓴이는 인증 서버의 public_id 로만 가리킨다.
 *   - 지운 댓글은 행을 없애지 않고 지운 시각을 적는다(deleted_at). 답글이 달린 댓글을 지워도 답글은 남는다.
 *     그 댓글의 자리는 "지운 댓글"로 보여 준다.
 */

import {
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
import { Post } from '../posts/post.entity.js';

/** 댓글의 최대 길이(글자) */
export const COMMENT_MAX_LENGTH = 2000;

@Entity('comments')
// 한 사람이 최근에 쓴 댓글을 센다. 쓰기 횟수 제한이 이 색인을 탄다(write-limits/)
@Index('ix_comments_author_id_created_at', ['authorId', 'createdAt'])
// 한 글의 댓글을 번호 순으로 읽고(parent_id 가 비어 있는 것), 댓글마다의 답글을 번호 순으로 읽는다.
// 댓글 목록의 쿼리 셋(댓글, 답글, 답글이 있는가)이 모두 이 색인을 탄다
@Index('ix_comments_post_id_parent_id_id', ['postId', 'parentId', 'id'])
export class Comment {
  @PrimaryGeneratedColumn('identity', {
    type: 'bigint',
    generatedIdentity: 'ALWAYS',
    primaryKeyConstraintName: 'pk_comments',
  })
  id: string;

  @Column({ name: 'post_id', type: 'bigint' })
  postId: string;

  /** 글은 행을 없애지 않는다(지운 시각만 적는다). 댓글이 있는 글의 행은 지울 수 없다(RESTRICT) */
  @ManyToOne(() => Post, { onDelete: 'RESTRICT' })
  @JoinColumn({ name: 'post_id', foreignKeyConstraintName: 'fk_comments_post' })
  post: Post;

  /** 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null 이다 */
  @Column({ name: 'parent_id', type: 'bigint', nullable: true })
  parentId: string | null;

  @ManyToOne(() => Comment, { onDelete: 'RESTRICT', nullable: true })
  @JoinColumn({
    name: 'parent_id',
    foreignKeyConstraintName: 'fk_comments_parent',
  })
  parent: Comment | null;

  /** 글쓴이. 인증 서버의 public_id */
  @Column({ name: 'author_id', type: 'uuid' })
  authorId: string;

  @Column({ type: 'text' })
  content: string;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  /** 마지막으로 고친 시각. 고친 적이 없으면 쓴 시각과 같다 */
  @UpdateDateColumn({ name: 'updated_at', type: 'timestamptz' })
  updatedAt: Date;

  /** 지운 시각. 지우지 않았으면 null 이다 */
  @DeleteDateColumn({ name: 'deleted_at', type: 'timestamptz' })
  deletedAt: Date | null;
}
