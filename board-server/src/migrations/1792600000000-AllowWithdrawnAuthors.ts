// board-server/src/migrations/1792600000000-AllowWithdrawnAuthors.ts

/**
 * 탈퇴한 사람의 번호를 비울 수 있게 한다(#603, docs/architecture/withdrawal.md).
 *
 * 글과 댓글의 글쓴이(author_id), 신고한 사람(reporter_id)을 비울 수 있다. 탈퇴를 받으면 그 사람의 번호를 비운다(withdrawals/).
 * 글, 댓글, 신고는 남는다. 함께한 사람의 대화이고 운영의 기록이라서다. 화면은 "탈퇴한 사용자"로 보인다.
 * 번호를 남기면 공개된 응답의 author_id 로 탈퇴한 사람의 글을 한데 모을 수 있다. 그래서 남기지 않는다.
 *
 * 되돌리면 다시 비울 수 없게 한다. 비운 줄이 하나라도 있으면 멈추고 아무것도 바꾸지 않는다.
 * 그 줄에 넣을 번호를 이 서버는 모른다. 처음부터 다시 하려면 스키마를 지우고 다시 만든다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AllowWithdrawnAuthors1792600000000 implements MigrationInterface {
  name = 'AllowWithdrawnAuthors1792600000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "posts" ALTER COLUMN "author_id" DROP NOT NULL
        `);
    await queryRunner.query(`
            ALTER TABLE "comments" ALTER COLUMN "author_id" DROP NOT NULL
        `);
    await queryRunner.query(`
            ALTER TABLE "reports" ALTER COLUMN "reporter_id" DROP NOT NULL
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM "posts" WHERE "author_id" IS NULL)
                    OR EXISTS (SELECT 1 FROM "comments" WHERE "author_id" IS NULL)
                    OR EXISTS (SELECT 1 FROM "reports" WHERE "reporter_id" IS NULL) THEN
                    RAISE EXCEPTION '탈퇴로 비운 줄이 있어 되돌리지 않는다';
                END IF;
            END;
            $$
        `);
    await queryRunner.query(`
            ALTER TABLE "reports" ALTER COLUMN "reporter_id" SET NOT NULL
        `);
    await queryRunner.query(`
            ALTER TABLE "comments" ALTER COLUMN "author_id" SET NOT NULL
        `);
    await queryRunner.query(`
            ALTER TABLE "posts" ALTER COLUMN "author_id" SET NOT NULL
        `);
  }
}
