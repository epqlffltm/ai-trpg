// board-server/src/migrations/1791779867393-AddAuthors.ts

/**
 * 글쓴이의 닉네임(authors) 테이블을 만든다. 사람마다 한 줄이다(src/authors/author.entity.ts).
 *
 * 엔티티에서 자동으로 만든 것을 그대로 쓴다. 지우는 색인이 없어 스키마 이름을 뺄 곳이 없다.
 * 이미 있는 글과 댓글의 글쓴이는 채우지 않는다. 이름을 모르니 null 로 나가고, 그 사람이 다시 들어오면 채워진다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddAuthors1791779867393 implements MigrationInterface {
  name = 'AddAuthors1791779867393';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "authors" (
                "user_id" uuid NOT NULL,
                "nickname" character varying(50) NOT NULL,
                "updated_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT "pk_authors" PRIMARY KEY ("user_id")
            )
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            DROP TABLE "authors"
        `);
  }
}
