// board-server/src/reports/report.entity.ts

/**
 * 신고 하나. reports 테이블의 모양이다. 글의 신고와 댓글의 신고를 한 테이블에 둔다.
 *
 *   - 무엇을 신고했는지는 post_id 와 comment_id 가운데 꼭 하나에 적는다(ck_reports_one_target).
 *     둘 다 외래 키라 없는 글이나 댓글을 가리킬 수 없다. "대상의 종류 + 번호" 한 칸으로 두면 외래 키를 걸 수 없다.
 *   - 글과 댓글은 지워도 행이 남는다(지운 시각만 적는다). 그래서 신고당한 것을 지워도 신고 기록은 남는다.
 *   - 같은 사람이 같은 것을 두 번 신고하지 못한다(유일 제약 둘). 비어 있는 칸(NULL)은 서로 겹치지 않으므로
 *     글의 신고와 댓글의 신고가 서로를 막지 않는다.
 *   - 운영자가 처리하면 처리한 시각, 처리한 사람, 결과를 함께 적는다. 셋은 함께 있거나 함께 없다.
 *     처리하지 않은 신고가 "열린 신고"다.
 *   - 신고는 지우지 않는다. 고치지도 않는다. 처리한 것만 적는다.
 */

import {
  Check,
  Column,
  CreateDateColumn,
  Entity,
  Index,
  JoinColumn,
  ManyToOne,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';
import { Comment } from '../comments/comment.entity.js';
import { Post } from '../posts/post.entity.js';
import { REPORT_OUTCOMES, REPORT_REASONS, sqlList } from './reports.policy.js';
// 타입만 가져온다(import type). 엔티티의 칸 타입으로만 쓴다
import type { ReportOutcome, ReportReason } from './reports.policy.js';

@Entity('reports')
// 글과 댓글 가운데 꼭 하나를 가리킨다
@Check('ck_reports_one_target', '("post_id" IS NULL) <> ("comment_id" IS NULL)')
@Check('ck_reports_reason', `"reason" IN (${sqlList(REPORT_REASONS)})`)
@Check(
  'ck_reports_outcome',
  `"outcome" IS NULL OR "outcome" IN (${sqlList(REPORT_OUTCOMES)})`,
)
// 처리한 시각, 처리한 사람, 결과는 함께 있거나 함께 없다
@Check(
  'ck_reports_handled_together',
  '("handled_at" IS NULL) = ("handled_by" IS NULL) AND ("handled_at" IS NULL) = ("outcome" IS NULL)',
)
@Unique('uq_reports_reporter_id_post_id', ['reporterId', 'postId'])
@Unique('uq_reports_reporter_id_comment_id', ['reporterId', 'commentId'])
// 한 사람이 최근에 한 신고를 센다. 신고 횟수 제한이 이 색인을 탄다(write-limits/)
@Index('ix_reports_reporter_id_created_at', ['reporterId', 'createdAt'])
// 한 글, 한 댓글의 신고를 읽고 처리한다. 각각 그 칸이 찬 행만 담는다
@Index('ix_reports_post_id', ['postId'], { where: '"post_id" IS NOT NULL' })
@Index('ix_reports_comment_id', ['commentId'], {
  where: '"comment_id" IS NOT NULL',
})
// 열린 신고를 모아 운영자의 목록을 만든다. 처리한 신고는 쌓여 가지만 이 색인에는 들지 않는다
@Index('ix_reports_open', ['createdAt'], { where: '"handled_at" IS NULL' })
export class Report {
  @PrimaryGeneratedColumn('identity', {
    type: 'bigint',
    generatedIdentity: 'ALWAYS',
    primaryKeyConstraintName: 'pk_reports',
  })
  id: string;

  /** 신고한 글. 댓글의 신고면 null 이다 */
  @Column({ name: 'post_id', type: 'bigint', nullable: true })
  postId: string | null;

  /** 글은 행을 없애지 않는다. 신고가 있는 글의 행은 지울 수 없다(RESTRICT) */
  @ManyToOne(() => Post, { onDelete: 'RESTRICT', nullable: true })
  @JoinColumn({ name: 'post_id', foreignKeyConstraintName: 'fk_reports_post' })
  post: Post | null;

  /** 신고한 댓글. 글의 신고면 null 이다 */
  @Column({ name: 'comment_id', type: 'bigint', nullable: true })
  commentId: string | null;

  @ManyToOne(() => Comment, { onDelete: 'RESTRICT', nullable: true })
  @JoinColumn({
    name: 'comment_id',
    foreignKeyConstraintName: 'fk_reports_comment',
  })
  comment: Comment | null;

  /** 신고한 사람. 인증 서버의 public_id. 탈퇴한 사람이면 null 이다(withdrawals/). 신고는 남는다 */
  @Column({ name: 'reporter_id', type: 'uuid', nullable: true })
  reporterId: string | null;

  @Column({ type: 'varchar', length: 20 })
  reason: ReportReason;

  /** 신고한 사람이 붙인 설명. 적지 않았으면 null 이다. 로그에 남기지 않는다 */
  @Column({ type: 'text', nullable: true })
  description: string | null;

  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  /** 운영자가 처리한 시각. 열린 신고면 null 이다 */
  @Column({ name: 'handled_at', type: 'timestamptz', nullable: true })
  handledAt: Date | null;

  /** 처리한 운영자. 인증 서버의 public_id */
  @Column({ name: 'handled_by', type: 'uuid', nullable: true })
  handledBy: string | null;

  /** 처리한 결과 */
  @Column({ type: 'varchar', length: 20, nullable: true })
  outcome: ReportOutcome | null;
}
