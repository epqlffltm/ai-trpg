// board-server/src/migrations/1791712910506-CreateBoardsPostsOperators.ts

/**
 * 게시판(boards), 글(posts), 운영자(operators) 테이블을 만든다.
 *
 * 엔티티에서 자동으로 만든 뒤(npm run migration:generate) 손으로 고친 곳이 하나 있다.
 * 색인을 지우는 줄에서 스키마 이름을 뺐다. 같은 파일을 개발용과 테스트용 스키마에 함께 쓴다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class CreateBoardsPostsOperators1791712910506 implements MigrationInterface {
  name = 'CreateBoardsPostsOperators1791712910506';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "boards" (
                "id" integer GENERATED ALWAYS AS IDENTITY NOT NULL,
                "slug" character varying(30) NOT NULL,
                "name" character varying(50) NOT NULL,
                "description" character varying(200) NOT NULL,
                "write_policy" character varying(20) NOT NULL,
                "position" integer NOT NULL,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT "uq_boards_slug" UNIQUE ("slug"),
                CONSTRAINT "ck_boards_write_policy" CHECK ("write_policy" IN ('member', 'operator')),
                CONSTRAINT "pk_boards" PRIMARY KEY ("id")
            )
        `);
    await queryRunner.query(`
            CREATE TABLE "operators" (
                "user_id" uuid NOT NULL,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT "pk_operators" PRIMARY KEY ("user_id")
            )
        `);
    await queryRunner.query(`
            CREATE TABLE "posts" (
                "id" bigint GENERATED ALWAYS AS IDENTITY NOT NULL,
                "board_id" integer NOT NULL,
                "author_id" uuid NOT NULL,
                "title" character varying(100) NOT NULL,
                "content" text NOT NULL,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "updated_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                "deleted_at" TIMESTAMP WITH TIME ZONE,
                CONSTRAINT "pk_posts" PRIMARY KEY ("id")
            )
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_posts_board_id_id" ON "posts" ("board_id", "id")
        `);
    await queryRunner.query(`
            ALTER TABLE "posts"
            ADD CONSTRAINT "fk_posts_board" FOREIGN KEY ("board_id") REFERENCES "boards"("id") ON DELETE RESTRICT ON UPDATE NO ACTION
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            ALTER TABLE "posts" DROP CONSTRAINT "fk_posts_board"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_posts_board_id_id"
        `);
    await queryRunner.query(`
            DROP TABLE "posts"
        `);
    await queryRunner.query(`
            DROP TABLE "operators"
        `);
    await queryRunner.query(`
            DROP TABLE "boards"
        `);
  }
}
