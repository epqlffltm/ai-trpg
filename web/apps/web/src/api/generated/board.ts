// web/apps/web/src/api/generated/board.ts
// docs/api/board.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/board/boards": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 게시판을 정해 둔 차례대로 모두 돌려준다. */
        get: operations["BoardsController_list"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/boards/{slug}/posts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 한 게시판의 글 목록을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 첫 쪽에는 고정한 글을 따로 싣는다. */
        get: operations["PostsController_list"];
        put?: never;
        /** 게시판에 글을 쓴다. 쓴 글을 돌려준다. */
        post: operations["PostsController_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/comments/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** 댓글을 지운다. 돌려줄 내용이 없다. */
        delete: operations["CommentsController_remove"];
        options?: never;
        head?: never;
        /** 댓글의 내용을 고친다. 고친 댓글을 돌려준다. */
        patch: operations["CommentsController_update"];
        trace?: never;
    };
    "/api/v1/board/comments/{id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 한 댓글에 걸린 신고들. */
        get: operations["ReportReviewsController_listForComment"];
        put?: never;
        /** 댓글을 신고한다. 답글도 같다. */
        post: operations["ReportsController_reportComment"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/comments/{id}/reports/outcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** 한 댓글에 걸린 열린 신고를 모두 처리한다. */
        put: operations["ReportReviewsController_handleComment"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 토큰이 유효하면 그 주인의 ID 와 운영자인지를 돌려준다. */
        get: operations["MeController_readMe"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/posts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 없는 게시판이면 404 다. */
        get: operations["PostsSearchController_find"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/posts/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 글 하나를 본문까지 돌려준다. */
        get: operations["PostsController_read"];
        put?: never;
        post?: never;
        /** 글을 지운다. 돌려줄 내용이 없다. */
        delete: operations["PostsController_remove"];
        options?: never;
        head?: never;
        /** 글을 고친다. 보낸 칸만 고친다. 고친 글을 돌려준다. */
        patch: operations["PostsController_update"];
        trace?: never;
    };
    "/api/v1/board/posts/{id}/pin": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** 글을 고정한다. */
        put: operations["PinsController_pin"];
        post?: never;
        /** 글의 고정을 푼다. */
        delete: operations["PinsController_unpin"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/posts/{id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 한 글에 걸린 신고들. */
        get: operations["ReportReviewsController_listForPost"];
        put?: never;
        /** 글을 신고한다. */
        post: operations["ReportsController_reportPost"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/posts/{id}/reports/outcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** 한 글에 걸린 열린 신고를 모두 처리한다. */
        put: operations["ReportReviewsController_handlePost"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/posts/{postId}/comments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다. */
        get: operations["CommentsController_list"];
        put?: never;
        /** 글에 댓글을 단다. parent_id 를 적으면 그 댓글에 답글을 단다. 쓴 댓글을 돌려준다. */
        post: operations["CommentsController_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 열린 신고의 목록. 신고당한 것마다 한 줄이다. */
        get: operations["ReportReviewsController_listOpen"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/board/service/users/{userId}/withdrawal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** 그 사람의 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 보낼 알림을 지운다. */
        post: operations["WithdrawalsController_receive"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 서버 프로세스가 요청을 받을 수 있으면 200 을 돌려준다.
         *
         *     DB 나 다른 서버의 상태는 보지 않는다. 그것까지 보면, DB 가 잠깐 느려졌을 때
         *     관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
         */
        get: operations["HealthController_check"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * DB 에 닿으면 200, 닿지 않으면 503 을 돌려준다.
         *
         *     왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다.
         *     로그에도 오류의 종류만 남긴다.
         *
         *     준비되지 않았다는 것은 오류가 아니라 이 API 의 답이다. 그래서 예외를 던지지 않고 상태 코드만 바꾼다.
         *     예외로 던지면 오류 응답의 모양({ detail })으로 바뀐다. 이 주소는 관리 도구가 읽는 것이라 답의 모양을 지킨다.
         */
        get: operations["ReadinessController_check"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        BoardResponse: {
            description: string;
            name: string;
            slug: string;
            /**
             * @description 누가 글을 쓸 수 있는가. member 는 로그인한 누구나, operator 는 운영자만
             * @enum {string}
             */
            write_policy: "operator" | "member";
        };
        CommentListResponse: {
            items: components["schemas"]["CommentThreadResponse"][];
            /** @description 다음 토막을 부를 때 after 에 넣을 값. 뒤에 더 없으면 null 이다 */
            next: string | null;
        };
        CommentResponse: {
            /** @description 글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null */
            author_id: string | null;
            /** @description 글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null */
            author_nickname: string | null;
            /** @description 글쓴이가 탈퇴했는가. 지운 댓글이면 false 다 */
            author_withdrawn: boolean;
            /** @description 내용. 지운 댓글이면 null */
            content: string | null;
            created_at: string;
            /** @description 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다 */
            deleted: boolean;
            id: string;
            /** @description 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null */
            parent_id: string | null;
            post_id: string;
            updated_at: string;
        };
        CommentThreadResponse: {
            /** @description 글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null */
            author_id: string | null;
            /** @description 글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null */
            author_nickname: string | null;
            /** @description 글쓴이가 탈퇴했는가. 지운 댓글이면 false 다 */
            author_withdrawn: boolean;
            /** @description 내용. 지운 댓글이면 null */
            content: string | null;
            created_at: string;
            /** @description 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다 */
            deleted: boolean;
            id: string;
            /** @description 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null */
            parent_id: string | null;
            post_id: string;
            replies: components["schemas"]["CommentResponse"][];
            updated_at: string;
        };
        CreateCommentDto: {
            /** @description 내용. 받은 그대로 저장한다 */
            content: string;
            /**
             * @description 답글이면 어느 댓글에 다는가. 적지 않거나 null 이면 글에 다는 댓글이다. 번호는 글자로 보낸다("57").
             *     null 을 받는 것은 화면이 "답글이 아님"을 null 로 보내기 쉬워서다
             */
            parent_id?: string | null;
        };
        CreatePostDto: {
            /** @description 본문. 받은 그대로 저장한다. 줄바꿈과 들여쓰기가 글의 일부다 */
            content: string;
            /** @description 제목. 앞뒤 빈칸은 떼고 저장한다 */
            title: string;
        };
        CreateReportDto: {
            /** @description 설명. 받은 그대로 저장한다. 적지 않거나 null 이면 설명이 없는 것이다 */
            description?: string | null;
            /**
             * @description 사유
             * @enum {string}
             */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
        };
        ErrorBody: {
            /** @description 무엇이 잘못됐는가. 화면에 그대로 보여 줄 수 있는 문장이다 */
            detail: string;
            /** @description 입력이 틀렸을 때만 있다. 칸의 이름마다 틀린 까닭들이다 */
            errors?: {
                [key: string]: string[];
            };
            /** @description 너무 자주 불러서 거절했을 때만 있다. 몇 초 뒤에 다시 부르면 되는가 */
            retry_after?: number;
        };
        HandleReportsDto: {
            /**
             * @description 처리한 결과. 조치함(actioned), 문제없음(dismissed)
             * @enum {string}
             */
            outcome: "actioned" | "dismissed";
        };
        HealthResponse: {
            /** @enum {string} */
            status: "ok";
        };
        MeResponse: {
            /** @description 운영자인가. 토큰의 roles 를 읽은 것이다 */
            is_operator: boolean;
            /** @description 인증 서버의 public_id */
            user_id: string;
        };
        OpenReportGroupPageResponse: {
            items: components["schemas"]["OpenReportGroupResponse"][];
            /** @description 몇 번째 쪽인가. 1 부터 센다 */
            page: number;
            /** @description 한 쪽에 몇 개를 담는가 */
            size: number;
            /** @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
            total: number;
        };
        OpenReportGroupResponse: {
            first_reported_at: string;
            last_reported_at: string;
            open_count: number;
            reasons: components["schemas"]["ReasonCountsResponse"];
            target: components["schemas"]["ReportTargetResponse"];
        };
        PinPostDto: {
            /**
             * @description 며칠 동안 고정하는가. 적지 않으면 DEFAULT_PIN_DAYS 다. 그날이 지나면 저절로 내려간다
             * @default 7
             */
            days: number;
        };
        PostListResponse: {
            items: components["schemas"]["PostSummaryResponse"][];
            /** @description 몇 번째 쪽인가. 1 부터 센다 */
            page: number;
            /** @description 지금 고정되어 있는 글들. 나중에 고정한 것부터다. 첫 쪽에만 싣는다. items 와 total 에는 들지 않는다 */
            pinned: components["schemas"]["PostSummaryResponse"][];
            /** @description 한 쪽에 몇 개를 담는가 */
            size: number;
            /** @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
            total: number;
        };
        PostResponse: {
            /** @description 글쓴이. 탈퇴한 사람이면 null 이다 */
            author_id: string | null;
            /** @description 글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이거나 탈퇴한 사람이면 null 이다 */
            author_nickname: string | null;
            /** @description 글쓴이가 탈퇴했는가 */
            author_withdrawn: boolean;
            /** @description 글이 있는 게시판의 주소 이름(slug) */
            board: string;
            /** @description 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다 */
            comment_count: number;
            content: string;
            created_at: string;
            id: string;
            /** @description 지금 고정되어 있는가 */
            pinned: boolean;
            /** @description 고정이 끝나는 시각. 고정되어 있지 않으면 null 이다 */
            pinned_until: string | null;
            title: string;
            updated_at: string;
        };
        PostSummaryPageResponse: {
            items: components["schemas"]["PostSummaryResponse"][];
            /** @description 몇 번째 쪽인가. 1 부터 센다 */
            page: number;
            /** @description 한 쪽에 몇 개를 담는가 */
            size: number;
            /** @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
            total: number;
        };
        PostSummaryResponse: {
            /** @description 글쓴이. 탈퇴한 사람이면 null 이다 */
            author_id: string | null;
            /** @description 글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이거나 탈퇴한 사람이면 null 이다 */
            author_nickname: string | null;
            /** @description 글쓴이가 탈퇴했는가 */
            author_withdrawn: boolean;
            /** @description 글이 있는 게시판의 주소 이름(slug) */
            board: string;
            /** @description 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다 */
            comment_count: number;
            created_at: string;
            id: string;
            /** @description 지금 고정되어 있는가 */
            pinned: boolean;
            /** @description 고정이 끝나는 시각. 고정되어 있지 않으면 null 이다 */
            pinned_until: string | null;
            title: string;
            updated_at: string;
        };
        ReadinessResponse: {
            /** @enum {string} */
            status: "ok" | "unavailable";
        };
        ReasonCountsResponse: {
            abuse: number;
            illegal: number;
            other: number;
            sexual: number;
            spam: number;
        };
        ReportPageResponse: {
            items: components["schemas"]["ReportResponse"][];
            /** @description 몇 번째 쪽인가. 1 부터 센다 */
            page: number;
            /** @description 한 쪽에 몇 개를 담는가 */
            size: number;
            /** @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다 */
            total: number;
        };
        ReportReceiptResponse: {
            created_at: string;
            id: string;
            /** @enum {string} */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
        };
        ReportResponse: {
            created_at: string;
            /** @description 신고한 사람이 붙인 설명. 적지 않았으면 null */
            description: string | null;
            /** @description 처리한 시각. 열린 신고면 null */
            handled_at: string | null;
            /** @description 처리한 운영자. 열린 신고면 null */
            handled_by: string | null;
            id: string;
            /**
             * @description 처리한 결과. 열린 신고면 null
             * @enum {string|null}
             */
            outcome: "actioned" | "dismissed" | null;
            /** @enum {string} */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
            /** @description 신고한 사람. 인증 서버의 public_id. 탈퇴한 사람이면 null 이다 */
            reporter_id: string | null;
        };
        ReportTargetResponse: {
            /** @description 지금 지워져 있는가. 지운 것에 걸린 신고도 처리해서 닫아야 목록에서 빠진다 */
            deleted: boolean;
            id: string;
            /** @description 글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호 */
            post_id: string;
            /** @enum {string} */
            type: "post" | "comment";
        };
        UpdateCommentDto: {
            content: string;
        };
        UpdatePostDto: {
            content?: string;
            title?: string;
        };
        WithdrawalDto: {
            /** @description 인증 서버가 계정을 비운 시각(ISO 8601, 시간대 포함) */
            withdrawn_at: string;
        };
        WithdrawalResponse: {
            /**
             * @description 반영했다. 이미 했거나 할 것이 없었던 것도 같다
             * @enum {string}
             */
            status: "processed";
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    BoardsController_list: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoardResponse"][];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsController_list: {
        parameters: {
            query?: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
            };
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostListResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsController_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                slug: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePostDto"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    CommentsController_remove: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    CommentsController_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateCommentDto"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportReviewsController_listForComment: {
        parameters: {
            query?: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
            };
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportPageResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportsController_reportComment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateReportDto"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReceiptResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportReviewsController_handleComment: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HandleReportsDto"];
            };
        };
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    MeController_readMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsSearchController_find: {
        parameters: {
            query: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
                /** @description 검색어. 빈칸으로 낱말을 나눈다. 모든 낱말이 제목이나 본문에 들어 있는 글을 찾는다 */
                q: string;
                /** @description 어느 게시판에서 찾는가. 주소 이름(slug)이다. 적지 않으면 모든 게시판에서 찾는다 */
                board?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostSummaryPageResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsController_read: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsController_remove: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PostsController_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdatePostDto"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PinsController_pin: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PinPostDto"];
            };
        };
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    PinsController_unpin: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportReviewsController_listForPost: {
        parameters: {
            query?: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
            };
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportPageResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportsController_reportPost: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateReportDto"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReceiptResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportReviewsController_handlePost: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HandleReportsDto"];
            };
        };
        responses: {
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    CommentsController_list: {
        parameters: {
            query?: {
                /** @description 이 번호의 댓글 다음부터 읽는다. 적지 않으면 처음부터다. 앞의 응답의 next 를 그대로 넣는다 */
                after?: string;
                /** @description 한 번에 댓글을 몇 개 담는가. 답글은 세지 않는다 */
                size?: number;
            };
            header?: never;
            path: {
                postId: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentListResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    CommentsController_create: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                postId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateCommentDto"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    ReportReviewsController_listOpen: {
        parameters: {
            query?: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpenReportGroupPageResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    WithdrawalsController_receive: {
        parameters: {
            query?: never;
            header: {
                /** @description 인증 서버의 서명(t=<초>,v1=<HMAC>). 비밀은 AUTH_SERVER_SECRET 이다. 틀리면 401 */
                "X-Service-Signature": string;
            };
            path: {
                userId: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WithdrawalDto"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WithdrawalResponse"];
                };
            };
            /** @description 오류. 상태 코드가 무엇이든 본문은 이 모양이다 */
            default: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ErrorBody"];
                };
            };
        };
    };
    HealthController_check: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    ReadinessController_check: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadinessResponse"];
                };
            };
        };
    };
}
