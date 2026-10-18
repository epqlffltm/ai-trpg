// board-server/test/data.ts

/**
 * 테스트가 DB 의 내용을 맞출 때 함께 쓰는 도구. 테스트용 스키마(board_test)에서만 돈다(test/app.ts 가 지킨다).
 *
 * 게시판(boards)은 건드리지 않는다. 마이그레이션이 넣은 것을 그대로 쓴다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { DataSource } from 'typeorm';
import { AuthorsService } from '../src/authors/authors.service.js';
import { forgetOperators, grantOperator, revokeOperator } from './tokens.js';

/**
 * 신고, 글, 댓글, 글쓴이의 닉네임, 알림의 발송함을 모두 비우고, 번호를 1 부터 다시 센다. 테스트마다 먼저 부른다.
 * 운영자 그룹(test/tokens.ts)도 비운다.
 *
 * 앞의 테스트가 남긴 글이 다음 테스트의 목록에 섞이지 않게 한다.
 * 신고는 글과 댓글을, 댓글은 글을 가리키므로 한 번에 비운다. 따로 비우면 DB 가 막는다.
 */
export async function clearData(app: NestExpressApplication): Promise<void> {
  await app
    .get(DataSource)
    .query(
      'TRUNCATE "reports", "comments", "posts", "authors", "outgoing_notifications" RESTART IDENTITY',
    );
  forgetOperators();
  // 서버는 최근에 적은 닉네임을 기억해 두고 다시 적지 않는다. 테이블을 비웠으니 그 기억도 비운다
  app.get(AuthorsService).forgetRecent();
}

/**
 * 사용자를 운영자로 만든다. userId 는 인증 서버의 public_id 다.
 * 인증 서버의 operators 그룹에 넣는 것과 같다. 그 뒤에 만든 토큰에 roles 가 실린다(test/tokens.ts).
 */
export function makeOperator(userId: string): void {
  grantOperator(userId);
}

/** 사용자를 운영자에서 내린다. 그 뒤에 만든 토큰부터 운영자가 아니다. */
export function removeOperator(userId: string): void {
  revokeOperator(userId);
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

/**
 * 이 사람이 쓴 글과 댓글, 한 신고의 시각을 seconds 초만큼 과거로 옮긴다. 그만큼 시간이 흐른 것처럼 만든다.
 * 쓰기 횟수 제한의 창이 지나가는 것을 기다리지 않고 본다.
 */
export async function ageWrites(
  app: NestExpressApplication,
  userId: string,
  seconds: number,
): Promise<void> {
  const dataSource = app.get(DataSource);
  const owners = [
    ['posts', 'author_id'],
    ['comments', 'author_id'],
    ['reports', 'reporter_id'],
  ];
  for (const [table, owner] of owners) {
    await dataSource.query(
      `UPDATE "${table}" SET "created_at" = "created_at" - make_interval(secs => $2) WHERE "${owner}" = $1`,
      [userId, seconds],
    );
  }
}

/** 글을 한꺼번에 많이 넣는다. API 를 거치지 않는다. 본문이 긴 글이 많을 때를 볼 때 쓴다. */
export async function insertManyPosts(
  app: NestExpressApplication,
  count: number,
  authorId: string,
): Promise<void> {
  await app.get(DataSource).query(
    `INSERT INTO "posts" ("board_id", "author_id", "title", "content")
     SELECT (SELECT "id" FROM "boards" WHERE "slug" = 'free'), $2, '글 ' || n, repeat('본문 글자 ', 400) || n
       FROM generate_series(1, $1) AS n`,
    [count, authorId],
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

/** 신고 하나의 행을 DB 에서 그대로 읽는다. 없으면 undefined 다. */
export async function readReportRow(
  app: NestExpressApplication,
  id: string,
): Promise<Record<string, unknown> | undefined> {
  const rows: Record<string, unknown>[] = await app
    .get(DataSource)
    .query('SELECT * FROM "reports" WHERE "id" = $1', [id]);
  return rows[0];
}

/** 글쓴이의 닉네임을 DB 에서 그대로 읽는다. 모르는 사람이면 undefined 다. */
export async function readAuthorRow(
  app: NestExpressApplication,
  userId: string,
): Promise<Record<string, unknown> | undefined> {
  const rows: Record<string, unknown>[] = await app
    .get(DataSource)
    .query('SELECT * FROM "authors" WHERE "user_id" = $1', [userId]);
  return rows[0];
}
