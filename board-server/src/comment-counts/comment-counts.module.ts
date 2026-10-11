// board-server/src/comment-counts/comment-counts.module.ts

/**
 * 글마다의 댓글 수를 세는 모듈. 글 모듈이 쓴다.
 *
 * 댓글 모듈(CommentsModule)에 두지 않고 따로 뺐다. 댓글 모듈은 글이 있는지 확인하려고 글 모듈을 가져다 쓴다.
 * 글 모듈이 댓글 수를 알려고 댓글 모듈을 가져다 쓰면 둘이 서로를 물고 돈다.
 * 이 모듈은 comments 테이블만 읽고 다른 모듈을 쓰지 않는다. 그래서 글 모듈이 가져다 써도 고리가 생기지 않는다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Comment } from '../comments/comment.entity.js';
import { CommentCountsService } from './comment-counts.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Comment])],
  providers: [CommentCountsService],
  exports: [CommentCountsService],
})
export class CommentCountsModule {}
