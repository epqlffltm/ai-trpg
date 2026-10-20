// board-server/src/posts/posts-search.service.ts

/**
 * 글을 검색한다. 읽기만 한다.
 *
 * 제목이나 본문에 낱말이 들어 있는지를 ILIKE '%낱말%' 로 본다. 대소문자를 가리지 않는다.
 * 색인을 타지 않는다. 부를 때마다 글을 훑는다. 글이 수만 개일 때까지는 이것으로 충분하다.
 *   - 한국어 전문 검색은 형태소를 나누는 확장이 있어야 한다. PostgreSQL 의 기본 이미지에는 없다.
 *   - pg_trgm(세 글자씩 잘라 만드는 색인)은 두 글자 검색어에 쓰이지 못한다. 한국어 검색어는 두 글자가 많다.
 * 느려지면 색인을 더한다. 쿼리와 API 는 그대로 둔다(README 의 설계 메모).
 *
 * 검색 하나가 DB 를 오래 붙잡지 못하게 시간 제한을 건다. 넘으면 DB 가 쿼리를 멈추고, 503 으로 답한다.
 * 검색은 로그인 없이 부른다. 누가 얼마나 부르는지를 세는 것은 프록시의 일이다. 여기서는 한 번의 값만 묶어 둔다.
 *
 * 검색마다 결과(success, timeout)와 걸린 시간을 센다(board_searches_total, board_search_duration_seconds).
 * timeout 이 늘면 색인이나 검색 엔진이 필요하다. 그 밖의 실패(DB 가 없다)는 세지 않는다. 요청의 5xx 로 보인다.
 */

import {
  Inject,
  Injectable,
  ServiceUnavailableException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import {
  Brackets,
  EntityManager,
  QueryFailedError,
  Repository,
  SelectQueryBuilder,
} from 'typeorm';
import { recordSearch, secondsSince } from '../observability/metrics.js';
import { offsetOf, Page, pageOf } from './page.js';
import { Post } from './post.entity.js';
import { containsPattern } from './search.js';

/** 검색 쿼리에 주는 시간(천분의 1초). 넘으면 DB 가 쿼리를 멈춘다 */
export const SEARCH_TIMEOUT_MS = 3000;
/** 위의 값을 바꿔 끼우는 이름. 테스트가 아주 짧은 시간을 넣어 본다 */
export const SEARCH_TIMEOUT = Symbol('SEARCH_TIMEOUT');
/** PostgreSQL 이 시간 제한(statement_timeout)으로 쿼리를 멈췄을 때의 오류 코드 */
const QUERY_CANCELED = '57014';

/** 검색이 시간 제한에 걸렸을 때의 응답. 원인(쿼리, 걸린 시간)은 싣지 않는다. */
export function searchTookTooLong(): ServiceUnavailableException {
  return new ServiceUnavailableException({
    detail: '검색이 오래 걸려 멈췄습니다. 검색어를 바꿔 다시 시도해 주세요.',
  });
}

/** 이 오류는 DB 가 시간 제한으로 쿼리를 멈춘 것인가. */
export function isStatementTimeout(error: unknown): boolean {
  if (!(error instanceof QueryFailedError)) {
    return false;
  }
  const driverError: unknown = error.driverError;
  return (
    typeof driverError === 'object' &&
    driverError !== null &&
    (driverError as { code?: unknown }).code === QUERY_CANCELED
  );
}

/** 무엇을 어디서 찾는가. */
export interface PostSearch {
  /** 찾는 낱말들. 모두 들어 있는 글이 나온다 */
  terms: readonly string[];
  /** 이 게시판에서만 찾는다. 없으면 모든 게시판에서 찾는다 */
  boardId?: number;
}

/**
 * 쿼리에 "이 낱말이 제목이나 본문에 들어 있다"는 조건을 하나 더한다.
 * 낱말은 값으로 넘긴다(:term0). SQL 의 글에 이어 붙이지 않는다.
 */
export function whereContains(
  query: SelectQueryBuilder<Post>,
  term: string,
  index: number,
): SelectQueryBuilder<Post> {
  const name = `term${index}`;
  // ESCAPE '\' 는 낱말 안의 \% 와 \_ 를 글자로 읽게 한다(search.ts 의 escapeLike)
  return query.andWhere(
    new Brackets((either) =>
      either
        .where(`post.title ILIKE :${name} ESCAPE '\\'`)
        .orWhere(`post.content ILIKE :${name} ESCAPE '\\'`),
    ),
    { [name]: containsPattern(term) },
  );
}

@Injectable()
export class PostsSearchService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    @Inject(SEARCH_TIMEOUT) private readonly timeoutMs: number,
  ) {}

  /**
   * 낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 번호가 큰 것(새 글)부터다. 본문은 읽지 않는다.
   * 지운 글은 나오지 않는다. 고정한 글은 다른 글과 같이 제 번호의 자리에 나온다.
   * 정해 둔 시간을 넘기면 503 이다.
   */
  async search(
    search: PostSearch,
    page: number,
    size: number,
  ): Promise<Page<Post>> {
    const started = performance.now();
    try {
      const [items, total] = await this.withTimeout((manager) =>
        this.matching(manager, search)
          .orderBy('post.id', 'DESC')
          .skip(offsetOf(page, size))
          .take(size)
          .getManyAndCount(),
      );
      recordSearch('success', secondsSince(started));
      return pageOf(items, page, size, total);
    } catch (error) {
      if (!isStatementTimeout(error)) {
        throw error;
      }
      recordSearch('timeout', secondsSince(started));
      throw searchTookTooLong();
    }
  }

  /**
   * 시간 제한을 건 채로 일을 한다. 제한은 이 일의 쿼리에만 걸린다.
   *
   * 트랜잭션 안에서 SET LOCAL 로 건다. 트랜잭션이 끝나면 풀린다. 그냥 SET 으로 걸면 연결에 남아서,
   * 풀에 돌아간 그 연결을 받은 다른 요청에도 걸린다.
   */
  private withTimeout<Result>(
    work: (manager: EntityManager) => Promise<Result>,
  ): Promise<Result> {
    return this.posts.manager.transaction(async (manager) => {
      // SET 은 값을 따로 넘기지 못한다. 숫자인 것을 확인하고 적는다
      await manager.query(
        `SET LOCAL statement_timeout = ${Math.trunc(this.timeoutMs)}`,
      );
      return work(manager);
    });
  }

  /** 조건에 맞는 글을 고르는 쿼리. 줄 세우기와 쪽 나누기는 부르는 쪽이 붙인다. */
  private matching(
    manager: EntityManager,
    search: PostSearch,
  ): SelectQueryBuilder<Post> {
    const query = manager
      .createQueryBuilder(Post, 'post')
      .select([
        'post.id',
        'post.boardId',
        'post.authorId',
        'post.title',
        'post.pinnedUntil',
        'post.createdAt',
        'post.updatedAt',
      ]);
    if (search.boardId !== undefined) {
      query.where('post.boardId = :boardId', { boardId: search.boardId });
    }
    return search.terms.reduce(whereContains, query);
  }
}
