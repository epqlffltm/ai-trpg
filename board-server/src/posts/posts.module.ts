// board-server/src/posts/posts.module.ts

/**
 * 글을 맡는 모듈. 게시판을 찾는 데 BoardsModule 을 쓴다. 운영자인지는 토큰이 알려 준다(auth/roles.ts).
 * 글을 고정하고 푸는 일(PinsService)도 여기에 있다. 고정은 글의 상태다.
 * 글을 찾는 일(PostsSearchService)도 여기에 있다.
 * 글에 달린 댓글의 수는 CommentCountsModule 이 세고, 글쓴이의 닉네임은 AuthorsModule 이 읽는다.
 * 댓글 모듈이 글이 있는지 확인할 때 PostsService 를 쓴다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { AuthorsModule } from '../authors/authors.module.js';
import { BoardsModule } from '../boards/boards.module.js';
import { CommentCountsModule } from '../comment-counts/comment-counts.module.js';
import { WriteLimitsModule } from '../write-limits/write-limits.module.js';
import { PinsController } from './pins.controller.js';
import { PinsService } from './pins.service.js';
import { Post } from './post.entity.js';
import { PostsSearchController } from './posts-search.controller.js';
import {
  PostsSearchService,
  SEARCH_TIMEOUT,
  SEARCH_TIMEOUT_MS,
} from './posts-search.service.js';
import { PostsController } from './posts.controller.js';
import { PostsService } from './posts.service.js';

@Module({
  imports: [
    TypeOrmModule.forFeature([Post]),
    BoardsModule,
    CommentCountsModule,
    WriteLimitsModule,
    AuthorsModule,
  ],
  controllers: [PostsController, PinsController, PostsSearchController],
  providers: [
    PostsService,
    PinsService,
    PostsSearchService,
    { provide: SEARCH_TIMEOUT, useValue: SEARCH_TIMEOUT_MS },
  ],
  exports: [PostsService],
})
export class PostsModule {}
