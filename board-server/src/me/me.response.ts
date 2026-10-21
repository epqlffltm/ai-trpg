// board-server/src/me/me.response.ts

/**
 * 토큰의 주인을 알리는 답의 모양. 이름은 게임 서버의 /me 와 같다.
 *
 * 컨트롤러와 따로 둔 이유: API 목록(docs/api/board.openapi.json)은 *.response.ts 의 클래스에서 응답의 칸을 읽는다(nest-cli.json).
 */

/** 토큰의 주인. */
export class MeResponse {
  /** 인증 서버의 public_id */
  user_id: string;
  /** 운영자인가. 토큰의 roles 를 읽은 것이다 */
  is_operator: boolean;
}
