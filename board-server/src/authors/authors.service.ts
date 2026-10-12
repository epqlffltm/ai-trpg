// board-server/src/authors/authors.service.ts

/**
 * 글쓴이의 닉네임을 적어 두고 읽는다.
 *
 * 적는 것: 로그인한 요청마다 토큰의 이름을 받는다(authors.interceptor.ts). 최근에 같은 이름을 적었으면 넘긴다.
 * 아니면 DB 에 적는다. DB 의 이름과 같으면 행을 고치지 않는다(WHERE ... IS DISTINCT FROM).
 * 읽는 것: 응답에 실을 글쓴이들의 이름을 쿼리 하나로 읽는다. 글 목록의 한 쪽에 글쓴이가 스무 명이어도 한 번이다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { Author } from './author.entity.js';
import {
  nicknameOf,
  nicknamesFrom,
  Nicknames,
  NO_NICKNAMES,
} from './nicknames.js';
import { RecentNicknames } from './recent-nicknames.js';

/** 최근에 적은 이름을 몇 명까지 기억하는가. 한 사람에 100바이트 남짓이라 1만 명이면 1MB 쯤이다 */
export const RECENT_NICKNAMES_MAX = 10_000;

/**
 * 이름을 적는 SQL. 처음 보는 사람이면 넣고, 아는 사람이면 이름이 다를 때만 고친다.
 * 테이블 이름에 스키마를 붙이지 않는다. 어느 스키마인지는 연결이 정한다
 */
const UPSERT_NICKNAME = `
  INSERT INTO "authors" ("user_id", "nickname") VALUES ($1, $2)
  ON CONFLICT ("user_id") DO UPDATE
     SET "nickname" = EXCLUDED."nickname", "updated_at" = now()
   WHERE "authors"."nickname" IS DISTINCT FROM EXCLUDED."nickname"
`;

@Injectable()
export class AuthorsService {
  private readonly recent = new RecentNicknames(RECENT_NICKNAMES_MAX);

  constructor(
    @InjectRepository(Author) private readonly authors: Repository<Author>,
  ) {}

  /** 이 사람의 이름을 적어 둔다. 최근에 같은 이름을 적었으면 DB 에 묻지 않는다. */
  async remember(userId: string, nickname: string): Promise<void> {
    if (this.recent.has(userId, nickname)) {
      return;
    }
    await this.authors.query(UPSERT_NICKNAME, [userId, nickname]);
    this.recent.remember(userId, nickname);
  }

  /**
   * 최근에 적은 이름의 기억을 모두 잊는다. 다음 요청부터 DB 에 다시 적는다.
   * 테이블을 밖에서 비웠을 때 부른다(테스트가 테이블을 비울 때). 기억만 믿고 적지 않으면 이름이 사라진 채로 남는다.
   */
  forgetRecent(): void {
    this.recent.clear();
  }

  /** 사람들의 이름을 한 번에 읽는다. 이름을 모르는 사람은 표에 없다. */
  async nicknamesOf(userIds: readonly string[]): Promise<Nicknames> {
    const unique = [...new Set(userIds)];
    if (unique.length === 0) {
      return NO_NICKNAMES;
    }
    const rows = await this.authors.find({
      select: { userId: true, nickname: true },
      where: { userId: In(unique) },
    });
    return nicknamesFrom(rows);
  }

  /** 한 사람의 이름. 모르면 null 이다. */
  async nicknameOf(userId: string): Promise<string | null> {
    return nicknameOf(await this.nicknamesOf([userId]), userId);
  }
}
