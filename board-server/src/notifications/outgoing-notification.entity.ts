// board-server/src/notifications/outgoing-notification.entity.ts

/**
 * 발송함의 한 줄. outgoing_notifications 테이블의 모양이다. 알림 서버에 보낼 알림 하나다(#385).
 *
 * 알림을 정한 일(댓글 쓰기)과 같은 트랜잭션에 적는다. 그래서 댓글만 남고 알림이 사라지거나,
 * 알림만 가고 댓글은 되돌려지는 일이 없다. 알림 서버를 부르는 것은 그 뒤에 뒤에서 한다(notification-dispatcher.ts).
 *
 *   - pending: 보낼 차례를 기다린다. 보내지 못하면(알림 서버가 죽었다) 기다리는 시간을 늘려 다시 보낸다
 *   - 보내면(알림 서버가 받았다) 줄을 지운다. 알림의 기록은 알림 서버에 있다
 *   - failed: 알림 서버가 받지 않았다(같은 열쇠로 다른 알림, 모양이 틀렸다). 버그다. 사람이 보도록 남긴다
 *   - 오래(7일) 보내지 못한 pending 은 보내지 않고 지운다
 *
 * 게임 서버의 발송함(trpg-server/app/notifications/models.py)과 같은 모양이다.
 */

import {
  Check,
  Column,
  CreateDateColumn,
  Entity,
  Index,
  PrimaryGeneratedColumn,
  Unique,
} from 'typeorm';

/** 알림 서버의 상한과 같다(notification-server/app/notifications/models.py) */
export const SOURCE_KEY_MAX_LENGTH = 128;
export const KIND_MAX_LENGTH = 64;
/** 보내지 못한 까닭의 이름의 길이 */
export const ERROR_MAX_LENGTH = 40;

/** 발송함의 한 줄의 상태. 보낸 줄은 지우므로 상태가 없다 */
export const OUTBOX_STATUSES = ['pending', 'failed'] as const;
export type OutboxStatus = (typeof OUTBOX_STATUSES)[number];

@Entity('outgoing_notifications')
@Unique('uq_outgoing_notifications_source_key', ['sourceKey'])
@Check('ck_outgoing_notifications_status', `"status" IN ('pending', 'failed')`)
@Check('ck_outgoing_notifications_attempts', '"attempts" >= 0')
// 보낼 차례가 된 것을 찾는다. 기다리는 것만 담는다
@Index('ix_outgoing_notifications_due', ['nextAttemptAt'], {
  where: `"status" = 'pending'`,
})
export class OutgoingNotification {
  @PrimaryGeneratedColumn('identity', {
    type: 'bigint',
    generatedIdentity: 'ALWAYS',
    primaryKeyConstraintName: 'pk_outgoing_notifications',
  })
  id: string;

  /** 알림 서버가 같은 알림을 알아보는 열쇠. "<kind>:<댓글 번호>" 다 */
  @Column({
    name: 'source_key',
    type: 'varchar',
    length: SOURCE_KEY_MAX_LENGTH,
  })
  sourceKey: string;

  /** 받는 사람. 인증 서버의 public_id */
  @Column({ name: 'user_id', type: 'uuid' })
  userId: string;

  /** 무슨 일인가. 점으로 나눈 소문자(post.commented) */
  @Column({ type: 'varchar', length: KIND_MAX_LENGTH })
  kind: string;

  /** 알림의 내용. 알림 서버가 그대로 사용자에게 내준다 */
  @Column({ type: 'jsonb' })
  payload: Record<string, unknown>;

  @Column({ type: 'varchar', length: 20, default: 'pending' })
  status: OutboxStatus;

  /** 보내지 못한 횟수. 다시 보내기까지 기다리는 시간이 이것으로 정해진다 */
  @Column({ type: 'integer', default: 0 })
  attempts: number;

  /** 다음에 보낼 시각. 비어 있으면 바로 보낸다(처음 적은 것) */
  @Column({ name: 'next_attempt_at', type: 'timestamptz', nullable: true })
  nextAttemptAt: Date | null;

  /** 적은 시각. 오래 보내지 못한 것을 지울 때 본다 */
  @CreateDateColumn({ name: 'created_at', type: 'timestamptz' })
  createdAt: Date;

  /** 마지막으로 보내지 못한 까닭(unavailable 의 이름이나 알림 서버의 답) */
  @Column({
    name: 'last_error',
    type: 'varchar',
    length: ERROR_MAX_LENGTH,
    nullable: true,
  })
  lastError: string | null;
}
