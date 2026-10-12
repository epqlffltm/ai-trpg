// board-server/src/posts/posts.service.ts

/**
 * 글을 읽고, 쓰고, 고치고, 지운다.
 *
 * 권한의 규칙은 여기에 없다(posts.policy.ts). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
 * 안 되면 거절하고, 되면 저장한다. 응답의 모양으로 바꾸는 일은 컨트롤러가 한다.
 *
 * 거절하는 차례는 "없는 글인가(404)" 다음에 "해도 되는가(403)"다.
 * 글은 누구나 읽을 수 있어서, 있는 글인지를 숨길 까닭이 없다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { FindOptionsWhere, IsNull, LessThanOrEqual, Repository } from 'typeorm';
import { Board } from '../boards/board.entity.js';
import { OperatorsService } from '../operators/operators.service.js';
import { WriteLimitsService } from '../write-limits/write-limits.service.js';
import { offsetOf, Page, pageOf } from './page.js';
import { Post } from './post.entity.js';
import {
  nothingToUpdate,
  notYourPostToDelete,
  notYourPostToEdit,
  operatorOnlyBoard,
  operatorOnlyDelete,
  postNotFound,
} from './posts.errors.js';
import {
  canDelete,
  canEdit,
  canWrite,
  isOperatorOnly,
  needsOperatorCheckToDelete,
} from './posts.policy.js';

/** 새 글에 적는 값. */
export interface NewPost {
  title: string;
  content: string;
}

/** 글에서 고칠 값. 적은 칸만 고친다. */
export interface PostChanges {
  title?: string;
  content?: string;
}

/**
 * 한 게시판의, 지금 고정되어 있지 않은 글을 고르는 조건. 고정한 적이 없거나 고정이 끝난 글이다.
 * 둘 중 하나면 되므로 조건이 둘이다(TypeORM 은 배열을 OR 로 읽는다).
 */
export function notPinnedIn(
  boardId: number,
  now: Date,
): FindOptionsWhere<Post>[] {
  return [
    { boardId, pinnedUntil: IsNull() },
    { boardId, pinnedUntil: LessThanOrEqual(now) },
  ];
}

/** 고칠 칸이 하나라도 있는가. */
export function hasChanges(changes: PostChanges): boolean {
  return changes.title !== undefined || changes.content !== undefined;
}

@Injectable()
export class PostsService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    private readonly operators: OperatorsService,
    private readonly writeLimits: WriteLimitsService,
  ) {}

  /**
   * 한 게시판의 글을 한 쪽 돌려준다. 번호가 큰 것(새 글)부터다. 본문은 읽지 않는다.
   *
   * 지운 글은 목록에도 전체 개수에도 들지 않는다.
   * 지금 고정되어 있는 글도 들지 않는다. 그 글들은 따로 읽어 목록의 위에 싣는다(pins.service.ts).
   * 고정이 끝난 글은 제 번호의 자리로 돌아온다.
   */
  async listIn(
    board: Board,
    page: number,
    size: number,
    now: Date,
  ): Promise<Page<Post>> {
    const [items, total] = await this.posts.findAndCount({
      select: {
        id: true,
        authorId: true,
        title: true,
        pinnedUntil: true,
        createdAt: true,
        updatedAt: true,
      },
      where: notPinnedIn(board.id, now),
      order: { id: 'DESC' },
      skip: offsetOf(page, size),
      take: size,
    });
    return pageOf(items, page, size, total);
  }

  /** 글 하나를 게시판과 함께 읽는다. 없거나 지운 글이면 404 다. */
  async get(id: string): Promise<Post> {
    const post = await this.posts.findOne({
      where: { id },
      relations: { board: true },
    });
    if (post === null) {
      throw postNotFound();
    }
    return post;
  }

  /** 게시판에 글을 쓴다. 운영자만 쓰는 게시판인데 운영자가 아니면 403, 너무 자주 쓰면 429 다. */
  async create(board: Board, authorId: string, input: NewPost): Promise<Post> {
    await this.ensureCanWrite(board, authorId);
    await this.writeLimits.ensureCanWritePost(authorId);
    const post = await this.posts.save(
      this.posts.create({
        boardId: board.id,
        authorId,
        title: input.title,
        content: input.content,
        pinnedAt: null,
        pinnedUntil: null,
      }),
    );
    post.board = board;
    return post;
  }

  /** 글을 고친다. 고칠 칸이 없으면 400, 없는 글이면 404, 글쓴이가 아니면 403 이다. */
  async update(
    id: string,
    userId: string,
    changes: PostChanges,
  ): Promise<Post> {
    if (!hasChanges(changes)) {
      throw nothingToUpdate();
    }
    const post = await this.get(id);
    if (!canEdit(post, userId)) {
      throw notYourPostToEdit();
    }
    post.title = changes.title ?? post.title;
    post.content = changes.content ?? post.content;
    return this.posts.save(post);
  }

  /**
   * 글을 지운다. 없는 글이면 404, 지울 수 없는 사람이면 403 이다. 행은 남기고 지운 시각을 적는다.
   * 고정한 글을 지우면 고정한 글의 목록에서도 빠진다. 지운 글은 어느 목록에도 들지 않는다.
   */
  async remove(id: string, userId: string): Promise<void> {
    const post = await this.get(id);
    const isOperator = await this.isOperatorIfNeeded(post, userId);
    if (!canDelete(post, post.board, userId, isOperator)) {
      throw isOperatorOnly(post.board)
        ? operatorOnlyDelete()
        : notYourPostToDelete();
    }
    await this.posts.softDelete({ id: post.id });
  }

  /** 이 게시판에 써도 되는지 확인한다. 안 되면 403 을 낸다. 운영자인지는 운영자만 쓰는 게시판일 때만 묻는다. */
  private async ensureCanWrite(board: Board, userId: string): Promise<void> {
    const isOperator =
      isOperatorOnly(board) && (await this.operators.isOperator(userId));
    if (!canWrite(board, isOperator)) {
      throw operatorOnlyBoard();
    }
  }

  /** 운영자인지 답한다. 지워도 되는지 아는 데 필요 없으면 DB 에 묻지 않고 아니라고 답한다. */
  private async isOperatorIfNeeded(
    post: Post,
    userId: string,
  ): Promise<boolean> {
    if (!needsOperatorCheckToDelete(post, post.board, userId)) {
      return false;
    }
    return this.operators.isOperator(userId);
  }
}
