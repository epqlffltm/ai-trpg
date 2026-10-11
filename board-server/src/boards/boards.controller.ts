// board-server/src/boards/boards.controller.ts

/**
 * 게시판 목록을 돌려주는 API. 로그인 없이 부를 수 있다.
 */

import { Controller, Get, HttpCode, HttpStatus } from '@nestjs/common';
import { Public } from '../auth/public.decorator.js';
import { BoardResponse, toBoardResponse } from './board.response.js';
import { BoardsService } from './boards.service.js';

@Controller('boards')
export class BoardsController {
  constructor(private readonly boards: BoardsService) {}

  /** 게시판을 정해 둔 차례대로 모두 돌려준다. */
  @Public()
  @Get()
  @HttpCode(HttpStatus.OK)
  async list(): Promise<BoardResponse[]> {
    const boards = await this.boards.list();
    return boards.map(toBoardResponse);
  }
}
