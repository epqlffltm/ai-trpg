// board-server/src/migrations/1791712910507-SeedBoards.ts

/**
 * 처음부터 있는 게시판 넷을 넣는다. 게시판은 운영자가 화면에서 만들지 않고 마이그레이션으로 넣는다.
 *
 * 게시판을 더하려면 이 파일을 고치지 않고 새 마이그레이션을 만든다. 이미 적용된 마이그레이션은 다시 돌지 않는다.
 * 주소의 이름(slug)은 한번 정하면 바꾸지 않는다. 글의 주소가 깨진다.
 */

import { MigrationInterface, QueryRunner } from 'typeorm';

/** 넣을 게시판들. 차례대로 slug, 이름, 소개, 누가 쓰는가, 목록에서의 차례다 */
const BOARDS = [
  ['notice', '공지사항', '운영자가 알리는 소식입니다.', 'operator', 1],
  ['event', '이벤트', '진행 중인 이벤트와 그 결과를 알립니다.', 'operator', 2],
  ['free', '자유 게시판', '자유롭게 이야기를 나누는 곳입니다.', 'member', 3],
  [
    'scenario',
    '시나리오 이야기',
    '시나리오에 대한 감상과 이야기를 나누는 곳입니다.',
    'member',
    4,
  ],
] as const;

export class SeedBoards1791712910507 implements MigrationInterface {
  name = 'SeedBoards1791712910507';

  public async up(queryRunner: QueryRunner): Promise<void> {
    for (const board of BOARDS) {
      await queryRunner.query(
        `INSERT INTO "boards" ("slug", "name", "description", "write_policy", "position") VALUES ($1, $2, $3, $4, $5)`,
        [...board],
      );
    }
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.query(`DELETE FROM "boards" WHERE "slug" = ANY($1)`, [
      BOARDS.map(([slug]) => slug),
    ]);
  }
}
