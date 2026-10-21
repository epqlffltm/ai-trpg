// board-server/src/posts/page.response.ts

/**
 * 쪽으로 나눈 목록의 응답에 들어가는 칸들. API 목록(docs/api/board.openapi.json)에 실린다.
 *
 * 셈과 모양은 page.ts 의 Page<Item> 이 정한다. 이것은 그 모양을 목록 도구가 읽을 수 있게 클래스로 적은 것이다.
 * 목록 도구(@nestjs/swagger)는 TypeScript 의 제네릭을 읽지 못한다. Page<Item> 을 그대로 두면 items 가 무엇의 목록인지 빠진다.
 * 그래서 쪽의 칸 셋은 여기에 한 번 적고, items 는 항목의 종류마다 이것을 이어받은 클래스에 적는다
 * (PostSummaryPageResponse, ReportPageResponse, OpenReportGroupPageResponse).
 * 그 클래스들은 Page<Item> 을 implements 한다. 두 모양이 어긋나면 빌드가 실패한다.
 */

/** 쪽의 칸들. 혼자 쓰지 않고 이어받아 쓴다. */
export abstract class PageFields {
  /** 몇 번째 쪽인가. 1 부터 센다 */
  page: number;
  /** 한 쪽에 몇 개를 담는가 */
  size: number;
  /** 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
  total: number;
}
