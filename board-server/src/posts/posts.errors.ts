// board-server/src/posts/posts.errors.ts

/**
 * 글을 다루다 거절할 때의 응답들. 문장을 한곳에 모아 둔다.
 */

import {
  BadRequestException,
  ConflictException,
  ForbiddenException,
  NotFoundException,
} from '@nestjs/common';

/** 그런 글이 없다. 지운 글도 없는 글이다. */
export function postNotFound(): NotFoundException {
  return new NotFoundException({ detail: '글을 찾을 수 없습니다.' });
}

/** 운영자만 쓰는 게시판에 운영자가 아닌 사람이 쓰려 했다. */
export function operatorOnlyBoard(): ForbiddenException {
  return new ForbiddenException({
    detail: '이 게시판에는 운영자만 글을 쓸 수 있습니다.',
  });
}

/** 남의 글을 고치려 했다. */
export function notYourPostToEdit(): ForbiddenException {
  return new ForbiddenException({ detail: '자신의 글만 고칠 수 있습니다.' });
}

/** 운영자만 쓰는 게시판의 제 글을, 운영자에서 내려온 뒤에 고치려 했다. */
export function operatorOnlyEdit(): ForbiddenException {
  return new ForbiddenException({
    detail: '이 게시판의 글은 지금 운영자인 글쓴이만 고칠 수 있습니다.',
  });
}

/** 남의 글을 지우려 했다. */
export function notYourPostToDelete(): ForbiddenException {
  return new ForbiddenException({ detail: '자신의 글만 지울 수 있습니다.' });
}

/** 고칠 칸을 하나도 보내지 않았다. */
export function nothingToUpdate(): BadRequestException {
  return new BadRequestException({ detail: '고칠 내용을 적어야 합니다.' });
}

/** 운영자만 지우는 게시판의 글을 운영자가 아닌 사람이 지우려 했다. */
export function operatorOnlyDelete(): ForbiddenException {
  return new ForbiddenException({
    detail: '이 게시판의 글은 운영자만 지울 수 있습니다.',
  });
}

/** 운영자가 아닌 사람이 글을 고정하거나 풀려 했다. */
export function operatorOnlyPin(): ForbiddenException {
  return new ForbiddenException({
    detail: '운영자만 글을 고정할 수 있습니다.',
  });
}

/** 이 게시판에 고정한 글이 이미 다 찼다. 같은 요청을 다시 보내도 되지 않는다. 하나를 풀어야 한다. */
export function pinLimitReached(): ConflictException {
  return new ConflictException({
    detail: '이 게시판에는 글을 더 고정할 수 없습니다.',
  });
}
