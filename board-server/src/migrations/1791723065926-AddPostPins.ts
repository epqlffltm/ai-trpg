// board-server/src/migrations/1791723065926-AddPostPins.ts

/**
 * 글(posts)에 고정을 적는 열 둘을 더한다. 고정한 시각(pinned_at)과 고정이 끝나는 시각(pinned_until)이다.
 *
 * 있던 글은 모두 고정하지 않은 글이 된다(두 열이 비어 있다). 채워 넣을 값이 없다.
 * 색인은 고정한 적이 있는 글만 담는다(WHERE pinned_until IS NOT NULL). 글의 대부분은 고정하지 않은 글이라 색인이 작다.
 * 끝나는 시각으로 잡았다. 고정한 글을 읽는 쿼리가 "끝나는 시각이 지금보다 뒤"로 고른다.
 *
 * 엔티티에서 자동으로 만든 뒤(npm run migration:generate) 손으로 고친 곳이 하나 있다.
 * 색인을 지우는 줄에서 스키마 이름을 뺐다. 같은 파일을 개발용과 테스트용 스키마에 함께 쓴다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddPostPins1791723065926 implements MigrationInterface {
  name = 'AddPostPins1791723065926';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "posts"
            ADD "pinned_at" TIMESTAMP WITH TIME ZONE
        `);
    await queryRunner.query(`
            ALTER TABLE "posts"
            ADD "pinned_until" TIMESTAMP WITH TIME ZONE
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_posts_board_id_pinned_until" ON "posts" ("board_id", "pinned_until")
            WHERE "pinned_until" IS NOT NULL
        `);
    await queryRunner.query(`
            ALTER TABLE "posts"
            ADD CONSTRAINT "ck_posts_pin_pair" CHECK (("pinned_at" IS NULL) = ("pinned_until" IS NULL))
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "posts" DROP CONSTRAINT "ck_posts_pin_pair"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_posts_board_id_pinned_until"
        `);
    await queryRunner.query(`
            ALTER TABLE "posts" DROP COLUMN "pinned_until"
        `);
    await queryRunner.query(`
            ALTER TABLE "posts" DROP COLUMN "pinned_at"
        `);
  }
}
