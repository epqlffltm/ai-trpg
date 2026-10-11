// board-server/src/posts/posts.module.ts

/**
 * 글을 맡는 모듈. 게시판을 찾는 데 BoardsModule 을, 운영자인지 묻는 데 OperatorsModule 을 쓴다.
 * 댓글 모듈이 글이 있는지 확인할 때 PostsService 를 쓴다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BoardsModule } from '../boards/boards.module.js';
import { OperatorsModule } from '../operators/operators.module.js';
import { Post } from './post.entity.js';
import { PostsController } from './posts.controller.js';
import { PostsService } from './posts.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Post]), BoardsModule, OperatorsModule],
  controllers: [PostsController],
  providers: [PostsService],
  exports: [PostsService],
})
export class PostsModule {}
