// board-server/src/posts/posts.module.ts

/**
 * 글을 맡는 모듈. 게시판을 찾는 데 BoardsModule 을, 운영자인지 묻는 데 OperatorsModule 을 쓴다.
 * 글을 고정하고 푸는 일(PinsService)도 여기에 있다. 고정은 글의 상태다.
 * 글에 달린 댓글의 수는 CommentCountsModule 이 센다.
 * 댓글 모듈이 글이 있는지 확인할 때 PostsService 를 쓴다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BoardsModule } from '../boards/boards.module.js';
import { CommentCountsModule } from '../comment-counts/comment-counts.module.js';
import { OperatorsModule } from '../operators/operators.module.js';
import { PinsController } from './pins.controller.js';
import { PinsService } from './pins.service.js';
import { Post } from './post.entity.js';
import { PostsController } from './posts.controller.js';
import { PostsService } from './posts.service.js';

@Module({
  imports: [
    TypeOrmModule.forFeature([Post]),
    BoardsModule,
    OperatorsModule,
    CommentCountsModule,
  ],
  controllers: [PostsController, PinsController],
  providers: [PostsService, PinsService],
  exports: [PostsService],
})
export class PostsModule {}
