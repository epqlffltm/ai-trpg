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
import { Repository } from 'typeorm';
import { Board } from '../boards/board.entity.js';
import { OperatorsService } from '../operators/operators.service.js';
import { offsetOf, Page, pageOf } from './page.js';
import { Post } from './post.entity.js';
import {
  nothingToUpdate,
  notYourPostToDelete,
  notYourPostToEdit,
  operatorOnlyBoard,
  postNotFound,
} from './posts.errors.js';
import {
  canDelete,
  canEdit,
  canWrite,
  isAuthor,
  isOperatorOnly,
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

/** 고칠 칸이 하나라도 있는가. */
export function hasChanges(changes: PostChanges): boolean {
  return changes.title !== undefined || changes.content !== undefined;
}

@Injectable()
export class PostsService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    private readonly operators: OperatorsService,
  ) {}

  /**
   * 한 게시판의 글을 한 쪽 돌려준다. 번호가 큰 것(새 글)부터다. 본문은 읽지 않는다.
   *
   * 지운 글은 목록에도 전체 개수에도 들지 않는다.
   */
  async listIn(board: Board, page: number, size: number): Promise<Page<Post>> {
    const [items, total] = await this.posts.findAndCount({
      select: {
        id: true,
        authorId: true,
        title: true,
        createdAt: true,
        updatedAt: true,
      },
      where: { boardId: board.id },
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

  /** 게시판에 글을 쓴다. 운영자만 쓰는 게시판인데 운영자가 아니면 403 이다. */
  async create(board: Board, authorId: string, input: NewPost): Promise<Post> {
    await this.ensureCanWrite(board, authorId);
    const post = await this.posts.save(
      this.posts.create({
        boardId: board.id,
        authorId,
        title: input.title,
        content: input.content,
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

  /** 글을 지운다. 없는 글이면 404, 글쓴이도 운영자도 아니면 403 이다. 행은 남기고 지운 시각을 적는다. */
  async remove(id: string, userId: string): Promise<void> {
    const post = await this.get(id);
    if (!canDelete(post, userId, await this.isOperatorIfNeeded(post, userId))) {
      throw notYourPostToDelete();
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

  /** 운영자인지 답한다. 글쓴이 자신이면 묻지 않는다. 글쓴이는 운영자가 아니어도 지울 수 있다. */
  private async isOperatorIfNeeded(
    post: Post,
    userId: string,
  ): Promise<boolean> {
    if (isAuthor(post, userId)) {
      return false;
    }
    return this.operators.isOperator(userId);
  }
}
