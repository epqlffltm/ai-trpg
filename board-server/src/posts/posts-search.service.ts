// board-server/src/posts/posts-search.service.ts

/**
 * 글을 검색한다. 읽기만 한다.
 *
 * 제목이나 본문에 낱말이 들어 있는지를 ILIKE '%낱말%' 로 본다. 대소문자를 가리지 않는다.
 * 색인을 타지 않는다. 부를 때마다 글을 훑는다. 글이 수만 개일 때까지는 이것으로 충분하다.
 *   - 한국어 전문 검색은 형태소를 나누는 확장이 있어야 한다. PostgreSQL 의 기본 이미지에는 없다.
 *   - pg_trgm(세 글자씩 잘라 만드는 색인)은 두 글자 검색어에 쓰이지 못한다. 한국어 검색어는 두 글자가 많다.
 * 느려지면 색인을 더한다. 쿼리와 API 는 그대로 둔다(README 의 설계 메모).
 */

import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Brackets, Repository, SelectQueryBuilder } from 'typeorm';
import { offsetOf, Page, pageOf } from './page.js';
import { Post } from './post.entity.js';
import { containsPattern } from './search.js';

/** 무엇을 어디서 찾는가. */
export interface PostSearch {
  /** 찾는 낱말들. 모두 들어 있는 글이 나온다 */
  terms: readonly string[];
  /** 이 게시판에서만 찾는다. 없으면 모든 게시판에서 찾는다 */
  boardId?: number;
}

/**
 * 쿼리에 "이 낱말이 제목이나 본문에 들어 있다"는 조건을 하나 더한다.
 * 낱말은 값으로 넘긴다(:term0). SQL 의 글에 이어 붙이지 않는다.
 */
export function whereContains(
  query: SelectQueryBuilder<Post>,
  term: string,
  index: number,
): SelectQueryBuilder<Post> {
  const name = `term${index}`;
  // ESCAPE '\' 는 낱말 안의 \% 와 \_ 를 글자로 읽게 한다(search.ts 의 escapeLike)
  return query.andWhere(
    new Brackets((either) =>
      either
        .where(`post.title ILIKE :${name} ESCAPE '\\'`)
        .orWhere(`post.content ILIKE :${name} ESCAPE '\\'`),
    ),
    { [name]: containsPattern(term) },
  );
}

@Injectable()
export class PostsSearchService {
  constructor(
    @InjectRepository(Post) private readonly posts: Repository<Post>,
  ) {}

  /**
   * 낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 번호가 큰 것(새 글)부터다. 본문은 읽지 않는다.
   * 지운 글은 나오지 않는다. 고정한 글은 다른 글과 같이 제 번호의 자리에 나온다.
   */
  async search(
    search: PostSearch,
    page: number,
    size: number,
  ): Promise<Page<Post>> {
    const [items, total] = await this.matching(search)
      .orderBy('post.id', 'DESC')
      .skip(offsetOf(page, size))
      .take(size)
      .getManyAndCount();
    return pageOf(items, page, size, total);
  }

  /** 조건에 맞는 글을 고르는 쿼리. 줄 세우기와 쪽 나누기는 부르는 쪽이 붙인다. */
  private matching(search: PostSearch): SelectQueryBuilder<Post> {
    const query = this.posts
      .createQueryBuilder('post')
      .select([
        'post.id',
        'post.boardId',
        'post.authorId',
        'post.title',
        'post.pinnedUntil',
        'post.createdAt',
        'post.updatedAt',
      ]);
    if (search.boardId !== undefined) {
      query.where('post.boardId = :boardId', { boardId: search.boardId });
    }
    return search.terms.reduce(whereContains, query);
  }
}
