// board-server/src/comments/comments.module.ts

/**
 * 댓글을 맡는 모듈. 글이 있는지 확인하는 데 PostsModule 을 쓴다. 운영자인지는 토큰이 알려 준다(auth/roles.ts).
 * 글쓴이의 닉네임은 AuthorsModule 에서 읽는다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AuthorsModule } from '../authors/authors.module.js';
import { PostsModule } from '../posts/posts.module.js';
import { WriteLimitsModule } from '../write-limits/write-limits.module.js';
import { Comment } from './comment.entity.js';
import { CommentsController } from './comments.controller.js';
import { CommentsService } from './comments.service.js';

@Module({
  imports: [
    TypeOrmModule.forFeature([Comment]),
    PostsModule,
    WriteLimitsModule,
    AuthorsModule,
  ],
  controllers: [CommentsController],
  providers: [CommentsService],
})
export class CommentsModule {}
