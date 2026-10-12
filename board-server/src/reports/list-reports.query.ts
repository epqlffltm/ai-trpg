// board-server/src/reports/list-reports.query.ts

/**
 * 신고 목록을 부를 때 주소에 붙이는 값(?page=2&size=20)의 모양과 규칙. 글 목록과 같다.
 */

import { ListPostsQuery } from '../posts/list-posts.query.js';

export class ListReportsQuery extends ListPostsQuery {}
