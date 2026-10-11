// board-server/src/comments/comments.service.ts

/**
 * 댓글과 답글을 읽고, 쓰고, 고치고, 지운다.
 *
 * 규칙은 여기에 없다(comments.policy.ts). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
 * 안 되면 거절하고, 되면 저장한다. 응답의 모양으로 바꾸는 일은 컨트롤러가 한다.
 *
 * 목록은 쿼리 둘로 읽는다. 글에 단 댓글을 한 토막 읽고, 그 댓글들의 답글을 한 번에 읽는다.
 * 댓글마다 답글을 따로 읽으면 댓글 스무 개에 쿼리가 스물한 번 나간다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { OperatorsService } from '../operators/operators.service.js';
import { PostsService } from '../posts/posts.service.js';
import { Comment } from './comment.entity.js';
import { CommentThread } from './comment.response.js';
import {
  cannotReplyToReply,
  commentNotFound,
  notYourCommentToDelete,
  notYourCommentToEdit,
  parentNotFound,
  tooManyReplies,
} from './comments.errors.js';
import {
  canDelete,
  canEdit,
  canHaveReplies,
  hasRoomForReply,
  isAuthor,
} from './comments.policy.js';
import { fetchCount, Slice, sliceOf } from './slice.js';
import { threadsOf } from './threads.js';

/** 새 댓글에 적는 값. parentId 가 있으면 답글이다. */
export interface NewComment {
  content: string;
  parentId?: string;
}

/**
 * 지운 댓글인데 살아 있는 답글이 달려 있는가를 묻는 조건. 댓글 목록의 쿼리에 끼운다.
 * 테이블 이름에 스키마를 붙이지 않는다. 어느 스키마인지는 연결이 정한다
 */
const HAS_LIVE_REPLY = `EXISTS (
  SELECT 1 FROM "comments" "reply"
  WHERE "reply"."post_id" = "comment"."post_id"
    AND "reply"."parent_id" = "comment"."id"
    AND "reply"."deleted_at" IS NULL
)`;

@Injectable()
export class CommentsService {
  constructor(
    @InjectRepository(Comment) private readonly comments: Repository<Comment>,
    private readonly posts: PostsService,
    private readonly operators: OperatorsService,
  ) {}

  /**
   * 한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다.
   *
   * after 가 있으면 그 번호의 댓글 다음부터다. 없는 글이면 404 다.
   * 지운 댓글은 뺀다. 다만 답글이 달린 댓글은 지웠어도 자리를 남긴다. 지운 답글은 뺀다.
   */
  async listIn(
    postId: string,
    after: string | undefined,
    size: number,
  ): Promise<Slice<CommentThread>> {
    await this.posts.get(postId);
    const fetched = await this.findComments(postId, after, fetchCount(size));
    const slice = sliceOf(fetched, size, (comment) => comment.id);
    const replies = await this.findReplies(
      postId,
      slice.items.map((comment) => comment.id),
    );
    return { items: threadsOf(slice.items, replies), next: slice.next };
  }

  /** 댓글 하나를 읽는다. 없거나 지운 댓글이면 404 다. */
  async get(id: string): Promise<Comment> {
    const comment = await this.comments.findOneBy({ id });
    if (comment === null) {
      throw commentNotFound();
    }
    return comment;
  }

  /**
   * 글에 댓글을 단다. parentId 가 있으면 그 댓글에 답글을 단다.
   *
   * 없는 글이면 404 다. 답글을 달 수 없는 댓글이면 400(없는 댓글, 답글에 다는 답글)이나 409(답글이 다 참)다.
   */
  async create(
    postId: string,
    authorId: string,
    input: NewComment,
  ): Promise<Comment> {
    await this.posts.get(postId);
    if (input.parentId !== undefined) {
      await this.ensureCanReplyTo(postId, input.parentId);
    }
    return this.comments.save(
      this.comments.create({
        postId,
        parentId: input.parentId ?? null,
        authorId,
        content: input.content,
      }),
    );
  }

  /** 댓글의 내용을 고친다. 없는 댓글이면 404, 글쓴이가 아니면 403 이다. */
  async update(id: string, userId: string, content: string): Promise<Comment> {
    const comment = await this.get(id);
    if (!canEdit(comment, userId)) {
      throw notYourCommentToEdit();
    }
    comment.content = content;
    return this.comments.save(comment);
  }

  /**
   * 댓글을 지운다. 없는 댓글이면 404, 글쓴이도 운영자도 아니면 403 이다. 행은 남기고 지운 시각을 적는다.
   *
   * 답글이 달린 댓글을 지워도 답글은 남는다. 목록에는 그 댓글의 자리가 "지운 댓글"로 나온다.
   */
  async remove(id: string, userId: string): Promise<void> {
    const comment = await this.get(id);
    const isOperator = await this.isOperatorIfNeeded(comment, userId);
    if (!canDelete(comment, userId, isOperator)) {
      throw notYourCommentToDelete();
    }
    await this.comments.softDelete({ id: comment.id });
  }

  /**
   * 글에 단 댓글을 번호 순으로 count 개까지 읽는다. after 가 있으면 그 번호보다 큰 것만이다.
   *
   * 지운 댓글도 살아 있는 답글이 달려 있으면 읽는다. 그래서 지운 것을 빼는 TypeORM 의 기본 동작을 끄고
   * (withDeleted) 조건을 직접 적는다.
   */
  private findComments(
    postId: string,
    after: string | undefined,
    count: number,
  ): Promise<Comment[]> {
    const query = this.comments
      .createQueryBuilder('comment')
      .withDeleted()
      .where('comment.postId = :postId', { postId })
      .andWhere('comment.parentId IS NULL')
      .andWhere(`(comment.deletedAt IS NULL OR ${HAS_LIVE_REPLY})`)
      .orderBy('comment.id', 'ASC')
      .limit(count);
    if (after !== undefined) {
      query.andWhere('comment.id > :after', { after });
    }
    return query.getMany();
  }

  /** 댓글들에 달린 답글을 한 번에 읽는다. 댓글별로, 번호 순이다. 지운 답글은 읽지 않는다. */
  private findReplies(postId: string, parentIds: string[]): Promise<Comment[]> {
    if (parentIds.length === 0) {
      return Promise.resolve([]);
    }
    return this.comments.find({
      where: { postId, parentId: In(parentIds) },
      order: { parentId: 'ASC', id: 'ASC' },
    });
  }

  /**
   * 이 댓글에 답글을 달아도 되는지 확인한다. 안 되면 예외를 낸다.
   *
   * 답글의 수는 세어 보고 넣는다. 그사이에 다른 요청이 답글을 달면 끝을 한둘 넘을 수 있다.
   * 이 끝은 응답이 한없이 커지는 것을 막으려는 것이라 그 정도는 넘어도 된다. 정확히 지키려면
   * 댓글의 행을 잠그고 세야 한다.
   */
  private async ensureCanReplyTo(
    postId: string,
    parentId: string,
  ): Promise<void> {
    const parent = await this.comments.findOneBy({ id: parentId, postId });
    if (parent === null) {
      throw parentNotFound();
    }
    if (!canHaveReplies(parent)) {
      throw cannotReplyToReply();
    }
    // 글 번호를 함께 적는다. 색인이 글 번호로 시작한다
    const replyCount = await this.comments.countBy({ postId, parentId });
    if (!hasRoomForReply(replyCount)) {
      throw tooManyReplies();
    }
  }

  /** 운영자인지 답한다. 글쓴이 자신이면 묻지 않는다. 글쓴이는 운영자가 아니어도 지울 수 있다. */
  private async isOperatorIfNeeded(
    comment: Comment,
    userId: string,
  ): Promise<boolean> {
    if (isAuthor(comment, userId)) {
      return false;
    }
    return this.operators.isOperator(userId);
  }
}
