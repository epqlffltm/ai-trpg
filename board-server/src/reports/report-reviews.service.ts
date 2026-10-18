// board-server/src/reports/report-reviews.service.ts

/**
 * 운영자가 신고를 읽고 처리한다. 신고하는 쪽은 reports.service.ts 다.
 *
 * 모두 운영자만 한다. 운영자인지를 가장 먼저 본다(403). 무엇이 얼마나 신고됐는지는 운영자만 알 일이다.
 * 그다음이 "없는 것인가(404)"다.
 *
 * 지운 글과 지운 댓글에 걸린 신고도 읽고 처리한다. 신고당한 것을 운영자가 지운 뒤에도 신고는 열려 있다.
 * 처리해서 닫아야 목록에서 빠진다. 지우는 일과 처리하는 일을 묶지 않았다. 지우지 않고 "문제없음"으로
 * 닫는 일도 있고, 글쓴이가 스스로 지우는 일도 있다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, IsNull, Repository } from 'typeorm';
import type { Actor } from '../auth/actor.js';
import { Comment } from '../comments/comment.entity.js';
import { commentNotFound } from '../comments/comments.errors.js';
import { offsetOf, Page, pageOf } from '../posts/page.js';
import { Post } from '../posts/post.entity.js';
import { postNotFound } from '../posts/posts.errors.js';
import {
  OpenGroupRow,
  openGroupOf,
  OpenReportGroup,
  reasonColumn,
} from './open-groups.js';
import { Report } from './report.entity.js';
import { TargetState } from './report.response.js';
import { ReportTarget, whereTarget } from './report-target.js';
import { noOpenReports, operatorOnlyReports } from './reports.errors.js';
import { REPORT_REASONS, ReportOutcome } from './reports.policy.js';

/** 신고당한 것을 가리키는 열쇠. 목록의 줄과 그것의 상태를 짝짓는다 */
export function targetKey(target: ReportTarget): string {
  return `${target.type}:${target.id}`;
}

/** 운영자의 목록 한 줄과 신고당한 것의 지금 상태. */
export interface DescribedGroup {
  group: OpenReportGroup;
  state: TargetState;
}

@Injectable()
export class ReportReviewsService {
  constructor(
    @InjectRepository(Report) private readonly reports: Repository<Report>,
    @InjectRepository(Post) private readonly posts: Repository<Post>,
    @InjectRepository(Comment) private readonly comments: Repository<Comment>,
  ) {}

  /**
   * 열린 신고를 신고당한 것마다 묶어 한 쪽 돌려준다. 가장 오래 기다린 것(처음 신고가 가장 이른 것)부터다.
   * 운영자가 아니면 403 이다.
   */
  async listOpen(
    actor: Actor,
    page: number,
    size: number,
  ): Promise<Page<DescribedGroup>> {
    ensureOperator(actor);
    const [groups, total] = await Promise.all([
      this.findOpenGroups(offsetOf(page, size), size),
      this.countOpenTargets(),
    ]);
    const states = await this.statesOf(groups.map((group) => group.target));
    const items = groups.map((group) => ({
      group,
      state: this.stateFrom(states, group.target),
    }));
    return pageOf(items, page, size, total);
  }

  /**
   * 글이나 댓글 하나에 걸린 신고를 모두(처리한 것도) 한 쪽 돌려준다. 최근 것부터다.
   * 운영자가 아니면 403, 그런 것이 없으면 404 다. 지운 것이어도 읽는다.
   */
  async listFor(
    target: ReportTarget,
    actor: Actor,
    page: number,
    size: number,
  ): Promise<Page<Report>> {
    ensureOperator(actor);
    await this.ensureExists(target);
    const [items, total] = await this.reports.findAndCount({
      where: whereTarget(target),
      order: { id: 'DESC' },
      skip: offsetOf(page, size),
      take: size,
    });
    return pageOf(items, page, size, total);
  }

  /**
   * 글이나 댓글 하나에 걸린 열린 신고를 모두 처리해서 닫는다.
   * 운영자가 아니면 403, 그런 것이 없거나 열린 신고가 없으면 404 다.
   *
   * 한 문장으로 닫으므로 같은 묶음의 신고는 처리한 시각이 같다. 닫은 뒤에 새 신고가 오면 다시 열린다.
   */
  async handle(
    target: ReportTarget,
    actor: Actor,
    outcome: ReportOutcome,
  ): Promise<void> {
    ensureOperator(actor);
    await this.ensureExists(target);
    const result = await this.reports.update(
      { ...whereTarget(target), handledAt: IsNull() },
      { handledAt: () => 'now()', handledBy: actor.userId, outcome },
    );
    if (result.affected === 0) {
      throw noOpenReports();
    }
  }

  /** 글이나 댓글이 있는지 확인한다. 지운 것도 있는 것이다. 없으면 404 를 낸다. */
  private async ensureExists(target: ReportTarget): Promise<void> {
    const where = { where: { id: target.id }, withDeleted: true };
    if (target.type === 'post') {
      if (!(await this.posts.exists(where))) {
        throw postNotFound();
      }
    } else if (!(await this.comments.exists(where))) {
      throw commentNotFound();
    }
  }

  /**
   * 열린 신고를 신고당한 것마다 묶어 읽는다. 처음 신고가 이른 것부터 count 개다.
   * 사유마다의 건수도 함께 센다(FILTER). 사유는 정해 둔 상수라 값으로 넘긴다.
   */
  private async findOpenGroups(
    offset: number,
    count: number,
  ): Promise<OpenReportGroup[]> {
    const query = this.reports
      .createQueryBuilder('report')
      .select('report.post_id', 'post_id')
      .addSelect('report.comment_id', 'comment_id')
      .addSelect('COUNT(*)', 'open_count')
      .addSelect('MIN(report.created_at)', 'first_reported_at')
      .addSelect('MAX(report.created_at)', 'last_reported_at');
    for (const reason of REPORT_REASONS) {
      query
        .addSelect(
          `COUNT(*) FILTER (WHERE report.reason = :${reasonColumn(reason)})`,
          reasonColumn(reason),
        )
        .setParameter(reasonColumn(reason), reason);
    }
    const rows = await query
      .where('report.handled_at IS NULL')
      .groupBy('report.post_id')
      .addGroupBy('report.comment_id')
      .orderBy('first_reported_at', 'ASC')
      // 처음 신고의 시각이 같으면 번호로 줄을 세운다. 쪽을 넘겨도 순서가 흔들리지 않게 한다
      .addOrderBy('report.post_id', 'ASC', 'NULLS LAST')
      .addOrderBy('report.comment_id', 'ASC', 'NULLS LAST')
      .offset(offset)
      .limit(count)
      .getRawMany<OpenGroupRow>();
    return rows.map(openGroupOf);
  }

  /**
   * 열린 신고가 걸린 것의 수. 글과 댓글을 따로 세어 더한다.
   * 한 신고는 둘 가운데 하나만 가리키고, 글의 번호와 댓글의 번호는 서로 다른 것을 센다.
   */
  private async countOpenTargets(): Promise<number> {
    const row = await this.reports
      .createQueryBuilder('report')
      .select(
        'COUNT(DISTINCT report.post_id) + COUNT(DISTINCT report.comment_id)',
        'total',
      )
      .where('report.handled_at IS NULL')
      .getRawOne<{ total: string }>();
    return Number(row?.total ?? 0);
  }

  /**
   * 신고당한 것들의 지금 상태(어느 글인가, 지웠는가)를 한 번에 읽는다. 글과 댓글을 한 번씩 묻는다.
   * 한 줄마다 물으면 한 쪽에 스무 번이 나간다.
   */
  private async statesOf(
    targets: ReportTarget[],
  ): Promise<Map<string, TargetState>> {
    const postIds = targets.filter((t) => t.type === 'post').map((t) => t.id);
    const commentIds = targets
      .filter((t) => t.type === 'comment')
      .map((t) => t.id);
    const [posts, comments] = await Promise.all([
      postIds.length === 0
        ? Promise.resolve([])
        : this.posts.find({
            select: { id: true, deletedAt: true },
            where: { id: In(postIds) },
            withDeleted: true,
          }),
      commentIds.length === 0
        ? Promise.resolve([])
        : this.comments.find({
            select: { id: true, postId: true, deletedAt: true },
            where: { id: In(commentIds) },
            withDeleted: true,
          }),
    ]);
    const states = new Map<string, TargetState>();
    for (const post of posts) {
      states.set(targetKey({ type: 'post', id: post.id }), {
        postId: post.id,
        deleted: post.deletedAt !== null,
      });
    }
    for (const comment of comments) {
      states.set(targetKey({ type: 'comment', id: comment.id }), {
        postId: comment.postId,
        deleted: comment.deletedAt !== null,
      });
    }
    return states;
  }

  /**
   * 목록의 한 줄에 맞는 상태를 꺼낸다. 글과 댓글은 행을 없애지 않고 외래 키가 신고를 지키므로 늘 있다.
   * 없으면 DB 가 약속을 어긴 것이다.
   */
  private stateFrom(
    states: Map<string, TargetState>,
    target: ReportTarget,
  ): TargetState {
    const state = states.get(targetKey(target));
    if (state === undefined) {
      throw new Error('신고당한 것을 찾지 못했다');
    }
    return state;
  }
}

/** 운영자인지 확인한다. 아니면 403 을 낸다. */
function ensureOperator(actor: Actor): void {
  if (!actor.isOperator) {
    throw operatorOnlyReports();
  }
}
