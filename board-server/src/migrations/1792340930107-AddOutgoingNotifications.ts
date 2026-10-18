// board-server/src/migrations/1792340930107-AddOutgoingNotifications.ts

/**
 * 알림의 발송함(outgoing_notifications)을 만든다(#385, src/notifications/outgoing-notification.entity.ts).
 *
 * 엔티티에서 자동으로 만든 것에서 색인을 지우는 줄의 스키마 이름만 뺐다.
 * 되돌리면 아직 보내지 못한 알림이 사라진다. 개발용 DB 에서만 되돌린다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddOutgoingNotifications1792340930107 implements MigrationInterface {
  name = 'AddOutgoingNotifications1792340930107';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "outgoing_notifications" (
                "id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
                "source_key" character varying(128) NOT NULL,
                "user_id" uuid NOT NULL,
                "kind" character varying(64) NOT NULL,
                "payload" jsonb NOT NULL,
                "status" character varying(20) NOT NULL DEFAULT 'pending',
                "attempts" integer NOT NULL DEFAULT '0',
                "next_attempt_at" TIMESTAMP WITH TIME ZONE,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "last_error" character varying(40),
                CONSTRAINT "uq_outgoing_notifications_source_key" UNIQUE ("source_key"),
                CONSTRAINT "ck_outgoing_notifications_attempts" CHECK ("attempts" >= 0),
                CONSTRAINT "ck_outgoing_notifications_status" CHECK ("status" IN ('pending', 'failed')),
                CONSTRAINT "pk_outgoing_notifications" PRIMARY KEY ("id")
            )
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_outgoing_notifications_due" ON "outgoing_notifications" ("next_attempt_at")
            WHERE "status" = 'pending'
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            DROP INDEX "ix_outgoing_notifications_due"
        `);
    await queryRunner.query(`
            DROP TABLE "outgoing_notifications"
        `);
  }
}
