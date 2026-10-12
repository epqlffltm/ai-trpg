// board-server/src/write-limits/write-limits.service.ts

/**
 * 글과 댓글을 너무 자주 쓰는지, 신고를 너무 자주 하는지 본다. 걸리면 429 를 낸다.
 *
 * 횟수를 따로 세어 두지 않는다. 이 사람이 최근에 쓴 글과 댓글, 한 신고의 행을 센다.
 *   - 세려는 것이 이미 DB 에 있다. Redis 같은 곳에 한 번 더 세어 두면 같은 숫자가 두 군데가 된다.
 *   - 서버를 다시 띄워도, 여러 대로 늘려도 맞다.
 *   - 지운 글과 댓글도 센다. 행이 남아 있다. "쓰고 지우고 또 쓰기"로 한도를 피하지 못한다.
 * 시각은 DB 의 것(now())으로만 견준다. 쓴 시각(created_at)을 DB 가 적으므로, 서버의 시계와 견주면 둘의 차이만큼 어긋난다.
 *
 * 세고 나서 쓰는 사이에 같은 사람의 다른 요청이 끼면 한두 개 넘을 수 있다. 막으려면 사용자마다 잠가야 한다.
 * 도배를 막는 데에는 "대략 이만큼"으로 충분하다.
 */

import { HttpException, Inject, Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ObjectLiteral, Repository } from 'typeorm';
import { Comment } from '../comments/comment.entity.js';
import { OperatorsService } from '../operators/operators.service.js';
import { Post } from '../posts/post.entity.js';
import { Report } from '../reports/report.entity.js';
import {
  tooManyComments,
  tooManyPosts,
  tooManyReports,
} from './write-limits.errors.js';
import { retryAfterSeconds, WriteLimit } from './write-limits.policy.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { WriteLimits } from './write-limits.policy.js';

/**
 * 한도를 바꿔 끼우는 이름. 서버는 정해 둔 값(WRITE_LIMITS)을 쓴다.
 * 테스트는 걸리지 않을 만큼 큰 값을 넣는다. 글을 수십 개 써 보는 테스트가 한도에 막히면 안 된다.
 */
export const WRITE_LIMITS_TOKEN = Symbol('WRITE_LIMITS');

/** 누가 쓴 행인지를 적은 칸. 글과 댓글은 글쓴이, 신고는 신고한 사람이다. 정해 둔 이름만 쿼리에 넣는다 */
type OwnerColumn = 'author_id' | 'reporter_id';

@Injectable()
export class WriteLimitsService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    @InjectRepository(Comment) private readonly comments: Repository<Comment>,
    @InjectRepository(Report) private readonly reports: Repository<Report>,
    private readonly operators: OperatorsService,
    @Inject(WRITE_LIMITS_TOKEN) private readonly limits: WriteLimits,
  ) {}

  /** 이 사람이 지금 글을 써도 되는지 확인한다. 너무 자주 썼으면 429 를 낸다. */
  async ensureCanWritePost(userId: string): Promise<void> {
    await this.ensureWithin(
      this.posts,
      'author_id',
      userId,
      this.limits.post,
      tooManyPosts,
    );
  }

  /** 이 사람이 지금 댓글을 써도 되는지 확인한다. 너무 자주 썼으면 429 를 낸다. */
  async ensureCanWriteComment(userId: string): Promise<void> {
    await this.ensureWithin(
      this.comments,
      'author_id',
      userId,
      this.limits.comment,
      tooManyComments,
    );
  }

  /** 이 사람이 지금 신고해도 되는지 확인한다. 너무 자주 했으면 429 를 낸다. */
  async ensureCanReport(userId: string): Promise<void> {
    await this.ensureWithin(
      this.reports,
      'reporter_id',
      userId,
      this.limits.report,
      tooManyReports,
    );
  }

  /**
   * 한도 안인지 확인한다. 넘었으면 운영자인지 보고, 아니면 거절한다.
   * 운영자인지는 한도를 넘었을 때만 묻는다. 대부분의 쓰기는 한도 안이라 쿼리가 하나로 끝난다.
   */
  private async ensureWithin<Written extends ObjectLiteral>(
    written: Repository<Written>,
    owner: OwnerColumn,
    userId: string,
    limit: WriteLimit,
    refuse: (retryAfter: number) => HttpException,
  ): Promise<void> {
    const retryAfter = await this.secondsUntilAllowed(
      written,
      owner,
      userId,
      limit,
    );
    if (retryAfter === undefined) {
      return;
    }
    if (await this.operators.isOperator(userId)) {
      return;
    }
    throw refuse(retryAfter);
  }

  /**
   * 한도에 걸렸으면 기다릴 시간(초)을, 아니면 undefined 를 돌려준다.
   *
   * 창 안에서 max 번째로 최근에 쓴 것을 찾는다. 있으면 이미 max 개를 쓴 것이다.
   * 그것이 창을 벗어나면 하나를 더 쓸 수 있다. 그때까지 남은 시간이 기다릴 시간이다.
   * 색인(author_id 나 reporter_id, created_at)을 탄다.
   */
  private async secondsUntilAllowed<Written extends ObjectLiteral>(
    written: Repository<Written>,
    owner: OwnerColumn,
    userId: string,
    limit: WriteLimit,
  ): Promise<number | undefined> {
    const row = await written
      .createQueryBuilder('written')
      // 지운 것도 센다. 신고에는 지운 것이 없다
      .withDeleted()
      .select(
        'EXTRACT(EPOCH FROM (written.created_at + make_interval(secs => :window) - now()))',
        'remaining',
      )
      .where(`written.${owner} = :userId`, { userId })
      .andWhere('written.created_at > now() - make_interval(secs => :window)')
      .setParameter('window', limit.windowSeconds)
      .orderBy('written.created_at', 'DESC')
      .offset(limit.max - 1)
      .limit(1)
      .getRawOne<{ remaining: string }>();
    return row === undefined ? undefined : retryAfterSeconds(row.remaining);
  }
}
