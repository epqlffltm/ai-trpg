// board-server/src/reports/reports.service.ts

/**
 * 글과 댓글을 신고한다. 신고한 사람의 쪽이다. 운영자가 읽고 처리하는 쪽은 report-reviews.service.ts 다.
 *
 * 규칙은 여기에 없다(reports.policy.ts). 여기서는 필요한 것을 DB 에서 읽어 그 규칙에 묻고,
 * 안 되면 거절하고, 되면 저장한다.
 *
 * 거절하는 차례는 "없는 것인가(404)", "자기 것인가(403)", "이미 신고했는가(409)", "너무 자주 하는가(429)"다.
 * 이미 신고한 것은 행을 만들지 않으므로 횟수를 세기 전에 거절한다.
 *
 * 지운 글과 지운 댓글은 신고하지 못한다. 읽을 수 없는 것이다. 지운 글에 달린 댓글도 같다.
 * 글과 댓글을 찾는 데 글 모듈과 댓글 모듈을 쓰지 않고 테이블을 바로 읽는다. 댓글 모듈은 글 모듈을 쓰므로,
 * 둘을 함께 가져다 쓰는 것보다 테이블을 읽는 편이 모듈 사이의 고리를 만들지 않는다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Comment } from '../comments/comment.entity.js';
import { commentNotFound } from '../comments/comments.errors.js';
import { Post } from '../posts/post.entity.js';
import { postNotFound } from '../posts/posts.errors.js';
import { WriteLimitsService } from '../write-limits/write-limits.service.js';
import { Report } from './report.entity.js';
import { ReportTarget, targetColumns, whereTarget } from './report-target.js';
import {
  alreadyReported,
  cannotReportOwn,
  isUniqueViolation,
} from './reports.errors.js';
import { canReport, ReportReason } from './reports.policy.js';

/** 새 신고에 적는 값. */
export interface NewReport {
  reason: ReportReason;
  description?: string | null;
}

@Injectable()
export class ReportsService {
  constructor(
    @InjectRepository(Report) private readonly reports: Repository<Report>,
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    @InjectRepository(Comment) private readonly comments: Repository<Comment>,
    private readonly writeLimits: WriteLimitsService,
  ) {}

  /**
   * 글이나 댓글을 신고한다. 없거나 지운 것이면 404, 자기 것이면 403, 이미 신고했으면 409,
   * 너무 자주 하면 429 다.
   */
  async file(
    target: ReportTarget,
    reporterId: string,
    input: NewReport,
  ): Promise<Report> {
    const authorId = await this.authorOf(target);
    if (!canReport(authorId, reporterId)) {
      throw cannotReportOwn(target.type);
    }
    if (await this.hasReported(target, reporterId)) {
      throw alreadyReported();
    }
    await this.writeLimits.ensureCanReport(reporterId);
    return this.save(target, reporterId, input);
  }

  /** 신고하는 것을 쓴 사람. 없거나 지운 것이면 404 를 낸다. */
  private authorOf(target: ReportTarget): Promise<string> {
    return target.type === 'post'
      ? this.postAuthor(target.id)
      : this.commentAuthor(target.id);
  }

  /** 글을 쓴 사람. 없거나 지운 글이면 404 다. */
  private async postAuthor(id: string): Promise<string> {
    const post = await this.posts.findOneBy({ id });
    if (post === null) {
      throw postNotFound();
    }
    return post.authorId;
  }

  /** 댓글을 쓴 사람. 없거나 지운 댓글, 지운 글에 달린 댓글이면 404 다. */
  private async commentAuthor(id: string): Promise<string> {
    const comment = await this.comments.findOneBy({ id });
    if (comment === null || !(await this.isLivePost(comment.postId))) {
      throw commentNotFound();
    }
    return comment.authorId;
  }

  /** 지우지 않은 글인가. */
  private isLivePost(id: string): Promise<boolean> {
    return this.posts.existsBy({ id });
  }

  /** 이 사람이 이것을 이미 신고했는가. 처리한 신고도 센다. 같은 것은 한 번만 신고한다. */
  private hasReported(
    target: ReportTarget,
    reporterId: string,
  ): Promise<boolean> {
    return this.reports.existsBy({ reporterId, ...whereTarget(target) });
  }

  /**
   * 신고를 저장한다. 같은 신고가 동시에 둘 들어오면 위의 확인을 함께 지나칠 수 있다.
   * 그때는 DB 의 유일 제약이 늦은 쪽을 막는다. 그것도 409 로 돌려준다.
   */
  private async save(
    target: ReportTarget,
    reporterId: string,
    input: NewReport,
  ): Promise<Report> {
    try {
      return await this.reports.save(
        this.reports.create({
          ...targetColumns(target),
          reporterId,
          reason: input.reason,
          description: input.description ?? null,
          handledAt: null,
          handledBy: null,
          outcome: null,
        }),
      );
    } catch (error) {
      if (isUniqueViolation(error)) {
        throw alreadyReported();
      }
      throw error;
    }
  }
}
