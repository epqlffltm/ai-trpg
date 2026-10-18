// board-server/src/posts/pins.service.ts

/**
 * 글을 고정하고, 풀고, 고정한 글을 읽는다.
 *
 * 규칙은 여기에 없다(pins.policy.ts). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고, 되면 저장한다.
 * 거절하는 차례는 "없는 글인가(404)", "해도 되는가(403)", "자리가 있는가(409)"다.
 *
 * 고정하고 푸는 것은 글을 고치는 것이 아니다. 고친 시각(updated_at)을 건드리지 않는다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { MoreThan, Not, Repository } from 'typeorm';
import { Board } from '../boards/board.entity.js';
import type { Actor } from '../auth/actor.js';
import { canPin, hasRoomToPin, pinEndsAt } from './pins.policy.js';
import { Post } from './post.entity.js';
import { operatorOnlyPin, pinLimitReached } from './posts.errors.js';
import { PostsService } from './posts.service.js';

@Injectable()
export class PinsService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    private readonly postsService: PostsService,
  ) {}

  /**
   * 한 게시판에 지금 고정되어 있는 글들. 나중에 고정한 것부터다. 본문은 읽지 않는다.
   * 끝나는 시각이 지난 글과 지운 글은 들지 않는다.
   */
  async listIn(board: Board, now: Date): Promise<Post[]> {
    return this.posts.find({
      select: {
        id: true,
        authorId: true,
        title: true,
        pinnedUntil: true,
        createdAt: true,
        updatedAt: true,
      },
      where: { boardId: board.id, pinnedUntil: MoreThan(now) },
      order: { pinnedAt: 'DESC', id: 'DESC' },
    });
  }

  /**
   * 글을 days 일 동안 고정한다. 이미 고정한 글이면 기간을 새로 잡는다. 맨 위로 올라온다.
   * 없는 글이면 404, 운영자가 아니면 403, 그 게시판에 고정한 글이 이미 다 찼으면 409 다.
   */
  async pin(id: string, actor: Actor, days: number, now: Date): Promise<void> {
    const post = await this.postsService.get(id);
    ensureCanPin(actor);
    if (!hasRoomToPin(await this.countOthersPinned(post, now))) {
      throw pinLimitReached();
    }
    await this.writePin(post.id, now, pinEndsAt(now, days));
  }

  /** 글의 고정을 푼다. 고정하지 않은 글이어도 오류가 아니다. 없는 글이면 404, 운영자가 아니면 403 이다. */
  async unpin(id: string, actor: Actor): Promise<void> {
    const post = await this.postsService.get(id);
    ensureCanPin(actor);
    await this.writePin(post.id, null, null);
  }

  /** 같은 게시판에서 이 글 말고 지금 고정되어 있는 글의 수. */
  private async countOthersPinned(post: Post, now: Date): Promise<number> {
    return this.posts.countBy({
      boardId: post.boardId,
      id: Not(post.id),
      pinnedUntil: MoreThan(now),
    });
  }

  /** 고정한 시각과 끝나는 시각을 적는다. 둘 다 null 이면 고정을 푼다. 고친 시각은 그대로 둔다. */
  private async writePin(
    id: string,
    pinnedAt: Date | null,
    pinnedUntil: Date | null,
  ): Promise<void> {
    await this.posts
      .createQueryBuilder()
      .update()
      // TypeORM 은 고칠 때마다 updated_at 을 지금으로 바꾼다. 제 값을 다시 적어 그대로 둔다
      .set({ pinnedAt, pinnedUntil, updatedAt: () => '"updated_at"' })
      .where({ id })
      .execute();
  }
}

/** 고정해도 되는 사람인지 확인한다. 아니면 403 을 낸다. */
function ensureCanPin(actor: Actor): void {
  if (!canPin(actor.isOperator)) {
    throw operatorOnlyPin();
  }
}
