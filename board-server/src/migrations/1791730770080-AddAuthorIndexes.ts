// board-server/src/migrations/1791730770080-AddAuthorIndexes.ts

/**
 * 글과 댓글에 (글쓴이, 쓴 시각) 색인을 더한다. "이 사람이 최근에 쓴 것"을 세는 데 쓴다(쓰기 횟수 제한).
 * 색인이 없으면 글을 쓸 때마다 그 테이블을 훑는다.
 *
 * 엔티티에서 자동으로 만든 뒤(npm run migration:generate) 손으로 고친 곳이 하나 있다.
 * 색인을 지우는 줄에서 스키마 이름을 뺐다. 같은 파일을 개발용과 테스트용 스키마에 함께 쓴다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddAuthorIndexes1791730770080 implements MigrationInterface {
  name = 'AddAuthorIndexes1791730770080';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE INDEX "ix_posts_author_id_created_at" ON "posts" ("author_id", "created_at")
        `);
    await queryRunner.query(`
            CREATE INDEX "ix_comments_author_id_created_at" ON "comments" ("author_id", "created_at")
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            DROP INDEX "ix_comments_author_id_created_at"
        `);
    await queryRunner.query(`
            DROP INDEX "ix_posts_author_id_created_at"
        `);
  }
}
