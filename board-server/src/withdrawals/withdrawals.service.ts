// board-server/src/withdrawals/withdrawals.service.ts

/**
 * 탈퇴한 사람의 것을 정리한다(#603, docs/architecture/withdrawal.md 의 게시판 줄). HTTP 를 모른다.
 *
 *   - 글과 댓글은 남긴다. 함께한 사람의 대화다. 글쓴이(author_id)만 비운다. 화면은 "탈퇴한 사용자"로 그린다
 *   - 신고는 남긴다. 운영의 기록이다. 신고한 사람(reporter_id)만 비운다. 처리한 운영자(handled_by)는 남긴다
 *   - 적어 둔 닉네임(authors)은 지운다
 *   - 그 사람에게 보낼 알림(발송함)은 지운다. 받을 사람이 없다
 *
 * 번호를 남기지 않는 까닭: 응답의 author_id 는 누구나 본다. 남기면 탈퇴한 사람의 글을 한데 모을 수 있다.
 * 비운 뒤에는 그 글과 댓글을 고칠 사람이 없다. 운영자만 지운다(posts.policy.ts, comments.policy.ts).
 *
 * 한 트랜잭션이다. 몇 번을 불러도 같다. 두 번째에는 바꿀 줄이 없다. 이 서버가 모르는 사람도 바꿀 줄이 없을 뿐이다.
 * SQL 을 직접 적는다. TypeORM 의 update 는 고친 시각(updated_at)을 함께 바꾸는데, 글쓴이를 비운 것은 글을 고친 것이 아니다.
 * 지운 글과 댓글(deleted_at)도 비운다. 테이블 이름에 스키마를 붙이지 않는다. 어느 스키마인지는 연결이 정한다.
 */

import { Injectable } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource, EntityManager } from 'typeorm';

/** 그 사람의 것을 정리한 수. 로그에 남긴다. 이미 정리했거나 모르는 사람이면 모두 0 이다. */
export interface Erased {
  /** 글쓴이를 비운 글(지운 글 포함) */
  posts: number;
  /** 글쓴이를 비운 댓글(지운 댓글 포함) */
  comments: number;
  /** 신고한 사람을 비운 신고 */
  reports: number;
  /** 지운 닉네임(0 이나 1) */
  authors: number;
  /** 지운 발송함의 알림 */
  notifications: number;
}

const BLANK_POST_AUTHOR = `
  UPDATE "posts" SET "author_id" = NULL WHERE "author_id" = $1 RETURNING "id"
`;
const BLANK_COMMENT_AUTHOR = `
  UPDATE "comments" SET "author_id" = NULL WHERE "author_id" = $1 RETURNING "id"
`;
const BLANK_REPORTER = `
  UPDATE "reports" SET "reporter_id" = NULL WHERE "reporter_id" = $1 RETURNING "id"
`;
const DELETE_AUTHOR = `
  DELETE FROM "authors" WHERE "user_id" = $1 RETURNING "user_id"
`;
const DELETE_OUTGOING = `
  DELETE FROM "outgoing_notifications" WHERE "user_id" = $1 RETURNING "id"
`;

/** 그 사람에 대한 문장 하나를 돌리고, 바꾸거나 지운 줄의 수를 돌려준다. 문장은 RETURNING 으로 줄마다 하나를 낸다. */
async function countRows(
  manager: EntityManager,
  sql: string,
  userId: string,
): Promise<number> {
  const rows: unknown[] = await manager.query(sql, [userId]);
  return rows.length;
}

@Injectable()
export class WithdrawalsService {
  constructor(@InjectDataSource() private readonly dataSource: DataSource) {}

  /** 그 사람의 것을 정리하고 정리한 수를 돌려준다. 한 트랜잭션이다. */
  erase(userId: string): Promise<Erased> {
    return this.dataSource.transaction(async (manager) => ({
      posts: await countRows(manager, BLANK_POST_AUTHOR, userId),
      comments: await countRows(manager, BLANK_COMMENT_AUTHOR, userId),
      reports: await countRows(manager, BLANK_REPORTER, userId),
      authors: await countRows(manager, DELETE_AUTHOR, userId),
      notifications: await countRows(manager, DELETE_OUTGOING, userId),
    }));
  }
}
