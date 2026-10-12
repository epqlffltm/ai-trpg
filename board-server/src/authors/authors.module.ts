// board-server/src/authors/authors.module.ts

/**
 * 글쓴이의 닉네임을 맡는 모듈. 글 모듈과 댓글 모듈이 응답에 이름을 실으려고 가져다 쓴다.
 *
 * authors 테이블만 읽고 쓰며 다른 모듈을 쓰지 않는다. 그래서 누가 가져다 써도 고리가 생기지 않는다.
 * 로그인한 요청마다 이름을 적어 두는 일(AuthorsInterceptor)을 앱 전체에 건다.
 */

import { Module } from '@nestjs/common';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Author } from './author.entity.js';
import { AuthorsInterceptor } from './authors.interceptor.js';
import { AuthorsService } from './authors.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Author])],
  providers: [
    AuthorsService,
    { provide: APP_INTERCEPTOR, useClass: AuthorsInterceptor },
  ],
  exports: [AuthorsService],
})
export class AuthorsModule {}
