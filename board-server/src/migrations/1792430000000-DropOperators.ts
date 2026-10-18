// board-server/src/migrations/1792430000000-DropOperators.ts

/**
 * 운영자 표(operators)를 지운다(#389). 누가 운영자인지는 이제 인증 서버가 정하고 토큰의 roles 로 알려 준다.
 *
 * 표에 있던 운영자는 옮기지 않는다. 인증 서버의 관리자 화면에서 그 사람을 operators 그룹에 넣는다(README 의 "운영자").
 * 되돌리면 빈 표가 생긴다. 지운 행은 돌아오지 않는다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

export class DropOperators1792430000000 implements MigrationInterface {
  name = 'DropOperators1792430000000';

  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            DROP TABLE "operators"
        `);
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`
            CREATE TABLE "operators" (
                "user_id" uuid NOT NULL,
                "created_at" TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
                CONSTRAINT "pk_operators" PRIMARY KEY ("user_id")
            )
        `);
  }
}
