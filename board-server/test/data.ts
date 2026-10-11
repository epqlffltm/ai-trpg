// board-server/test/data.ts

/**
 * 테스트가 DB 의 내용을 맞출 때 함께 쓰는 도구. 테스트용 스키마(board_test)에서만 돈다(test/app.ts 가 지킨다).
 *
 * 게시판(boards)은 건드리지 않는다. 마이그레이션이 넣은 것을 그대로 쓴다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { DataSource } from 'typeorm';

/**
 * 글, 댓글, 운영자를 모두 비우고, 번호를 1 부터 다시 센다. 테스트마다 먼저 부른다.
 *
 * 앞의 테스트가 남긴 글이 다음 테스트의 목록에 섞이지 않게 한다.
 * 댓글은 글을 가리키므로 둘을 한 번에 비운다. 따로 비우면 DB 가 막는다.
 */
export async function clearData(app: NestExpressApplication): Promise<void> {
  await app
    .get(DataSource)
    .query('TRUNCATE "comments", "posts", "operators" RESTART IDENTITY');
}

/** 사용자를 운영자로 만든다. userId 는 인증 서버의 public_id 다. */
export async function makeOperator(
  app: NestExpressApplication,
  userId: string,
): Promise<void> {
  await app
    .get(DataSource)
    .query('INSERT INTO "operators" ("user_id") VALUES ($1)', [userId]);
}

/** 사용자를 운영자에서 내린다. */
export async function removeOperator(
  app: NestExpressApplication,
  userId: string,
): Promise<void> {
  await app
    .get(DataSource)
    .query('DELETE FROM "operators" WHERE "user_id" = $1', [userId]);
}

/**
 * 고정한 글의 끝나는 시각을 지난 시각으로 바꾼다. 시간이 흘러 고정이 끝난 것처럼 만든다.
 * 고정한 시각도 그만큼 앞으로 옮긴다. 끝나는 시각이 고정한 시각보다 앞서는 행은 있을 수 없다.
 */
export async function expirePin(
  app: NestExpressApplication,
  id: string,
): Promise<void> {
  await app.get(DataSource).query(
    `UPDATE "posts"
        SET "pinned_at" = now() - interval '8 days', "pinned_until" = now() - interval '1 second'
      WHERE "id" = $1`,
    [id],
  );
}

/** 글 하나의 행을 DB 에서 그대로 읽는다. 지운 글도 읽는다. 없으면 undefined 다. */
export async function readPostRow(
  app: NestExpressApplication,
  id: string,
): Promise<Record<string, unknown> | undefined> {
  const rows: Record<string, unknown>[] = await app
    .get(DataSource)
    .query('SELECT * FROM "posts" WHERE "id" = $1', [id]);
  return rows[0];
}

/** 댓글 하나의 행을 DB 에서 그대로 읽는다. 지운 댓글도 읽는다. 없으면 undefined 다. */
export async function readCommentRow(
  app: NestExpressApplication,
  id: string,
): Promise<Record<string, unknown> | undefined> {
  const rows: Record<string, unknown>[] = await app
    .get(DataSource)
    .query('SELECT * FROM "comments" WHERE "id" = $1', [id]);
  return rows[0];
}
