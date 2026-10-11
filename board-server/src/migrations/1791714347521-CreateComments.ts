// board-server/src/migrations/1791714347521-CreateComments.ts

/**
 * 댓글(comments) 테이블을 만든다. 댓글과 답글을 한 테이블에 둔다. 답글은 parent_id 로 댓글을 가리킨다.
 *
 * 엔티티에서 자동으로 만든 뒤(npm run migration:generate) 손으로 고친 곳이 하나 있다.
 * 색인을 지우는 줄에서 스키마 이름을 뺐다. 같은 파일을 개발용과 테스트용 스키마에 함께 쓴다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateComments1791714347521 implements MigrationInterface {
  name = 'CreateComments1791714347521';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "comments" (
                "id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
                "post_id" bigint NOT NULL,
                "parent_id" bigint,
                "author_id" uuid NOT NULL,
                "content" text NOT NULL,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "updated_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "deleted_at" TIMESTAMP WITH TIME ZONE,
                CONSTRAINT "pk_comments" PRIMARY KEY ("id")
            )
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_comments_post_id_parent_id_id" ON "comments" ("post_id", "parent_id", "id")
        `);
    await queryRunner.query(`
            ALTER TABLE "comments"
            ADD CONSTRAINT "fk_comments_post" FOREIGN KEY ("post_id") REFERENCES "posts"("id") ON DELETE RESTRICT ON UPDATE NO ACTION
        `);
    await queryRunner.query(`
            ALTER TABLE "comments"
            ADD CONSTRAINT "fk_comments_parent" FOREIGN KEY ("parent_id") REFERENCES "comments"("id") ON DELETE RESTRICT ON UPDATE NO ACTION
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "comments" DROP CONSTRAINT "fk_comments_parent"
        `);
    await queryRunner.query(`
            ALTER TABLE "comments" DROP CONSTRAINT "fk_comments_post"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_comments_post_id_parent_id_id"
        `);
    await queryRunner.query(`
            DROP TABLE "comments"
        `);
  }
}
