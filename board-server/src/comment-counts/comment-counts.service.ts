// board-server/src/comment-counts/comment-counts.service.ts

/**
 * 글에 달린 댓글의 수를 센다. 읽기만 한다.
 *
 * 수를 글에 적어 두지 않고(posts.comment_count 같은 열) 물을 때마다 센다.
 *   - 실제 행을 세므로 수가 틀릴 수 없다. 적어 두면 댓글을 쓰고 지울 때마다 함께 고쳐야 하고,
 *     어긋났을 때 다시 맞추는 도구도 있어야 한다.
 *   - 글 목록 한 쪽에 쿼리가 하나 는다. 글마다 하나씩이 아니다. 그 쪽의 글 번호를 모아 한 번에 센다.
 *     색인(post_id, parent_id, id)의 앞머리(post_id)를 탄다.
 * "댓글 많은 순"으로 줄을 세워야 하면 그때 적어 두는 쪽으로 옮긴다. 응답의 모양은 그대로다.
 *
 * 세는 것은 살아 있는 댓글과 답글이다. 지운 것은 세지 않는다.
 * 답글이 남아 자리만 보이는 지운 댓글도 세지 않는다. 그 답글들은 센다.
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { In, Repository } from 'typeorm';
import { Comment } from '../comments/comment.entity.js';
import { CommentCounts, CountRow, countsFrom } from './counts.js';

@Injectable()
export class CommentCountsService {
  constructor(
    @InjectRepository(Comment) private readonly comments: Repository<Comment>,
  ) {}

  /** 글 하나의 댓글 수. */
  async countFor(postId: string): Promise<number> {
    return this.comments.countBy({ postId });
  }

  /** 여러 글의 댓글 수를 한 번에 센다. 글이 없으면 DB 에 묻지 않는다. */
  async countForMany(postIds: readonly string[]): Promise<CommentCounts> {
    if (postIds.length === 0) {
      return countsFrom([]);
    }
    const rows = await this.comments
      .createQueryBuilder('comment')
      .select('comment.postId', 'postId')
      .addSelect('COUNT(*)', 'count')
      // 지운 댓글은 TypeORM 이 뺀다(deleted_at IS NULL). 엔티티에 지운 시각의 칸이 있어서다
      .where({ postId: In([...postIds]) })
      .groupBy('comment.postId')
      .getRawMany<CountRow>();
    return countsFrom(rows);
  }
}
