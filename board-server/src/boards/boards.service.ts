// board-server/src/boards/boards.service.ts

/**
 * 게시판을 읽는다. 게시판을 만들거나 고치는 일은 없다. 그것은 마이그레이션이 한다.
 */

import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Board } from './board.entity.js';

/** 그런 게시판이 없을 때의 응답. */
export function boardNotFound(): NotFoundException {
  return new NotFoundException({ detail: '게시판을 찾을 수 없습니다.' });
}

@Injectable()
export class BoardsService {
  constructor(
    @InjectRepository(Board) private readonly boards: Repository<Board>,
  ) {}

  /** 게시판을 모두 돌려준다. 정해 둔 차례(position)대로다. */
  list(): Promise<Board[]> {
    return this.boards.find({ order: { position: 'ASC', id: 'ASC' } });
  }

  /** 주소의 이름(slug)으로 게시판을 찾는다. 없으면 404 다. */
  async getBySlug(slug: string): Promise<Board> {
    const board = await this.boards.findOneBy({ slug });
    if (board === null) {
      throw boardNotFound();
    }
    return board;
  }
}
