// board-server/src/boards/boards.module.ts

/**
 * 게시판을 맡는 모듈. 글 모듈이 게시판을 찾을 때 BoardsService 를 쓴다.
 */

import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Board } from './board.entity.js';
import { BoardsController } from './boards.controller.js';
import { BoardsService } from './boards.service.js';

@Module({
  imports: [TypeOrmModule.forFeature([Board])],
  controllers: [BoardsController],
  providers: [BoardsService],
  exports: [BoardsService],
})
export class BoardsModule {}
