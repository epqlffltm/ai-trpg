// board-server/src/migrations/1791777701944-AddReports.ts

/**
 * 신고(reports) 테이블을 만든다. 글의 신고와 댓글의 신고를 한 테이블에 둔다(src/reports/report.entity.ts).
 *
 * 엔티티에서 자동으로 만든 뒤(npm run migration:generate) 손으로 고친 곳이 하나 있다.
 * 색인을 지우는 줄에서 스키마 이름을 뺐다. 같은 파일을 개발용과 테스트용 스키마에 함께 쓴다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddReports1791777701944 implements MigrationInterface {
  name = 'AddReports1791777701944';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "reports" (
                "id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
                "post_id" bigint,
                "comment_id" bigint,
                "reporter_id" uuid NOT NULL,
                "reason" character varying(20) NOT NULL,
                "description" text,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "handled_at" TIMESTAMP WITH TIME ZONE,
                "handled_by" uuid,
                "outcome" character varying(20),
                CONSTRAINT "uq_reports_reporter_id_comment_id" UNIQUE ("reporter_id", "comment_id"),
                CONSTRAINT "uq_reports_reporter_id_post_id" UNIQUE ("reporter_id", "post_id"),
                CONSTRAINT "ck_reports_handled_together" CHECK (
                    ("handled_at" IS NULL) = ("handled_by" IS NULL)
                    AND ("handled_at" IS NULL) = ("outcome" IS NULL)
                ),
                CONSTRAINT "ck_reports_outcome" CHECK (
                    "outcome" IS NULL
                    OR "outcome" IN ('actioned', 'dismissed')
                ),
                CONSTRAINT "ck_reports_reason" CHECK (
                    "reason" IN ('spam', 'abuse', 'sexual', 'illegal', 'other')
                ),
                CONSTRAINT "ck_reports_one_target" CHECK (("post_id" IS NULL) <> ("comment_id" IS NULL)),
                CONSTRAINT "pk_reports" PRIMARY KEY ("id")
            )
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_reports_open" ON "reports" ("created_at")
            WHERE "handled_at" IS NULL
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_reports_comment_id" ON "reports" ("comment_id")
            WHERE "comment_id" IS NOT NULL
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_reports_post_id" ON "reports" ("post_id")
            WHERE "post_id" IS NOT NULL
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_reports_reporter_id_created_at" ON "reports" ("reporter_id", "created_at")
        `);
    await queryRunner.query(`
            ALTER TABLE "reports"
            ADD CONSTRAINT "fk_reports_post" FOREIGN KEY ("post_id") REFERENCES "posts"("id") ON DELETE RESTRICT ON UPDATE NO ACTION
        `);
    await queryRunner.query(`
            ALTER TABLE "reports"
            ADD CONSTRAINT "fk_reports_comment" FOREIGN KEY ("comment_id") REFERENCES "comments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "reports" DROP CONSTRAINT "fk_reports_comment"
        `);
    await queryRunner.query(`
            ALTER TABLE "reports" DROP CONSTRAINT "fk_reports_post"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_reports_reporter_id_created_at"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_reports_post_id"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_reports_comment_id"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_reports_open"
        `);
    await queryRunner.query(`
            DROP TABLE "reports"
        `);
  }
}
