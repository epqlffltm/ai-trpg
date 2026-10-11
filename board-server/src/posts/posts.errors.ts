// board-server/src/posts/posts.errors.ts

/**
 * 글을 다루다 거절할 때의 응답들. 문장을 한곳에 모아 둔다.
 */

import {
  BadRequestException,
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

/** 남의 글을 지우려 했다. */
export function notYourPostToDelete(): ForbiddenException {
  return new ForbiddenException({ detail: '자신의 글만 지울 수 있습니다.' });
}

/** 고칠 칸을 하나도 보내지 않았다. */
export function nothingToUpdate(): BadRequestException {
  return new BadRequestException({ detail: '고칠 내용을 적어야 합니다.' });
}
