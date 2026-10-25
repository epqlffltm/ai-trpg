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
        /**
         * List Boards
         * @description 게시판들을 정해 둔 차례대로 돌려준다.
         */
        get: operations["list_boards_api_v1_board_boards_get"];
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
        /**
         * List Posts
         * @description 한 게시판의 글 목록을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 첫 쪽에는 고정한 글을 따로 싣는다.
         */
        get: operations["list_posts_api_v1_board_boards__slug__posts_get"];
        put?: never;
        /**
         * Create Post
         * @description 게시판에 글을 쓴다. 쓴 글을 돌려준다.
         */
        post: operations["create_post_api_v1_board_boards__slug__posts_post"];
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
        /**
         * Delete Comment
         * @description 댓글을 지운다. 돌려줄 내용이 없다.
         */
        delete: operations["delete_comment_api_v1_board_comments__id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Comment
         * @description 댓글의 내용을 고친다. 고친 댓글을 돌려준다.
         */
        patch: operations["update_comment_api_v1_board_comments__id__patch"];
        trace?: never;
    };
    "/api/v1/board/comments/{id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Comment Reports
         * @description 한 댓글에 걸린 신고들.
         */
        get: operations["list_comment_reports_api_v1_board_comments__id__reports_get"];
        put?: never;
        /**
         * Report Comment
         * @description 댓글을 신고한다. 답글도 같다.
         */
        post: operations["report_comment_api_v1_board_comments__id__reports_post"];
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
        /**
         * Handle Comment Reports
         * @description 한 댓글에 걸린 열린 신고를 모두 처리한다.
         */
        put: operations["handle_comment_reports_api_v1_board_comments__id__reports_outcome_put"];
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
        /**
         * Read Me
         * @description 토큰의 주인의 ID 와 운영자인지를 돌려준다.
         */
        get: operations["read_me_api_v1_board_me_get"];
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
        /**
         * Search Posts
         * @description 낱말이 모두 들어 있는 글을 한 쪽 돌려준다. 새 글부터다. 본문은 싣지 않는다. 없는 게시판이면 404 다.
         */
        get: operations["search_posts_api_v1_board_posts_get"];
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
        /**
         * Read Post
         * @description 글 하나를 본문까지 돌려준다.
         */
        get: operations["read_post_api_v1_board_posts__id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Post
         * @description 글을 지운다. 돌려줄 내용이 없다.
         */
        delete: operations["delete_post_api_v1_board_posts__id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Post
         * @description 글을 고친다. 보낸 칸만 고친다. 고친 글을 돌려준다.
         */
        patch: operations["update_post_api_v1_board_posts__id__patch"];
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
        /**
         * Pin Post
         * @description 글을 고정한다. 본문 없이 부르면 7일이다.
         */
        put: operations["pin_post_api_v1_board_posts__id__pin_put"];
        post?: never;
        /**
         * Unpin Post
         * @description 글의 고정을 푼다.
         */
        delete: operations["unpin_post_api_v1_board_posts__id__pin_delete"];
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
        /**
         * List Post Reports
         * @description 한 글에 걸린 신고들.
         */
        get: operations["list_post_reports_api_v1_board_posts__id__reports_get"];
        put?: never;
        /**
         * Report Post
         * @description 글을 신고한다. 접수했다는 것만 돌려준다.
         */
        post: operations["report_post_api_v1_board_posts__id__reports_post"];
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
        /**
         * Handle Post Reports
         * @description 한 글에 걸린 열린 신고를 모두 처리한다.
         */
        put: operations["handle_post_reports_api_v1_board_posts__id__reports_outcome_put"];
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
        /**
         * List Comments
         * @description 한 글의 댓글을 한 토막 돌려준다. 먼저 쓴 것부터고, 댓글마다 답글이 모두 붙어 있다.
         */
        get: operations["list_comments_api_v1_board_posts__postId__comments_get"];
        put?: never;
        /**
         * Create Comment
         * @description 글에 댓글을 단다. parent_id 를 적으면 그 댓글에 답글을 단다. 쓴 댓글을 돌려준다.
         */
        post: operations["create_comment_api_v1_board_posts__postId__comments_post"];
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
        /**
         * List Open Reports
         * @description 열린 신고의 목록. 신고당한 것마다 한 줄이다.
         */
        get: operations["list_open_reports_api_v1_board_reports_get"];
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
        /**
         * Receive
         * @description 그 사람의 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 보낼 알림을 지운다.
         */
        post: operations["receive_api_v1_board_service_users__userId__withdrawal_post"];
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
         * Check Health
         * @description 서버 프로세스가 요청을 받을 수 있으면 200 을 돌려준다.
         *
         *     DB 나 다른 서버의 상태는 보지 않는다. 그것까지 보면, DB 가 잠깐 느려졌을 때
         *     관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
         */
        get: operations["check_health_health_get"];
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
         * Check Readiness
         * @description DB 에 3초 안에 닿으면 200, 아니면 503 을 돌려준다.
         *
         *     왜 닿지 않는지는 응답에 싣지 않는다. 오류 문구에는 DB 의 주소와 계정 이름이 들어 있다.
         *     원인은 서버의 로그에 남긴다. 오류의 종류만 적는다.
         */
        get: operations["check_readiness_health_ready_get"];
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
        /**
         * BoardResponse
         * @description 게시판 하나.
         */
        BoardResponse: {
            /** Description */
            description: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Write Policy
             * @enum {string}
             */
            write_policy: "member" | "operator";
        };
        /**
         * CommentListResponse
         * @description 댓글 목록의 한 토막.
         */
        CommentListResponse: {
            /** Items */
            items: components["schemas"]["CommentThreadResponse"][];
            /**
             * Next
             * @description 다음 토막을 부를 때 after 에 넣을 값. 뒤에 더 없으면 null 이다
             */
            next: string | null;
        };
        /**
         * CommentResponse
         * @description 댓글 하나.
         */
        CommentResponse: {
            /**
             * Author Id
             * @description 글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null
             */
            author_id: string | null;
            /**
             * Author Nickname
             * @description 글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null
             */
            author_nickname: string | null;
            /**
             * Author Withdrawn
             * @description 글쓴이가 탈퇴했는가. 지운 댓글이면 false 다
             */
            author_withdrawn: boolean;
            /**
             * Content
             * @description 내용. 지운 댓글이면 null
             */
            content: string | null;
            /** Created At */
            created_at: string;
            /**
             * Deleted
             * @description 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다
             */
            deleted: boolean;
            /** Id */
            id: string;
            /**
             * Parent Id
             * @description 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null
             */
            parent_id: string | null;
            /** Post Id */
            post_id: string;
            /** Updated At */
            updated_at: string;
        };
        /**
         * CommentThreadResponse
         * @description 목록의 한 줄. 글에 단 댓글 하나와 거기 달린 답글들이다.
         */
        CommentThreadResponse: {
            /**
             * Author Id
             * @description 글쓴이. 지운 댓글이거나 탈퇴한 사람이면 null
             */
            author_id: string | null;
            /**
             * Author Nickname
             * @description 글쓴이의 닉네임. 지운 댓글이거나, 이 서버가 이름을 모르는 사람이거나, 탈퇴한 사람이면 null
             */
            author_nickname: string | null;
            /**
             * Author Withdrawn
             * @description 글쓴이가 탈퇴했는가. 지운 댓글이면 false 다
             */
            author_withdrawn: boolean;
            /**
             * Content
             * @description 내용. 지운 댓글이면 null
             */
            content: string | null;
            /** Created At */
            created_at: string;
            /**
             * Deleted
             * @description 지운 댓글인가. 답글이 달려 있어 자리만 남은 것이다
             */
            deleted: boolean;
            /** Id */
            id: string;
            /**
             * Parent Id
             * @description 답글이면 어느 댓글에 단 것인가. 글에 단 댓글이면 null
             */
            parent_id: string | null;
            /** Post Id */
            post_id: string;
            /** Replies */
            replies: components["schemas"]["CommentResponse"][];
            /** Updated At */
            updated_at: string;
        };
        /**
         * CreateCommentDto
         * @description 댓글을 쓸 때 받는 값. 어느 글인지는 주소에 있고, 글쓴이는 토큰에서 안다.
         */
        CreateCommentDto: {
            /**
             * Content
             * @description 내용. 받은 그대로 저장한다
             */
            content: string;
            /**
             * Parent Id
             * @description 답글이면 어느 댓글에 다는가. 적지 않거나 null 이면 글에 다는 댓글이다. 번호는 글자로 보낸다("57").
             *     null 을 받는 것은 화면이 "답글이 아님"을 null 로 보내기 쉬워서다
             */
            parent_id?: string | null;
        };
        /**
         * CreatePostDto
         * @description 글을 쓸 때 받는 값. 어느 게시판인지는 주소에 있고, 글쓴이는 토큰에서 안다.
         */
        CreatePostDto: {
            /**
             * Content
             * @description 본문. 받은 그대로 저장한다. 줄바꿈과 들여쓰기가 글의 일부다
             */
            content: string;
            /**
             * Title
             * @description 제목. 앞뒤 빈칸은 떼고 저장한다
             */
            title: string;
        };
        /**
         * CreateReportDto
         * @description 신고할 때 받는 값. 무엇을 신고하는지는 주소에 있고, 신고한 사람은 토큰에서 안다.
         */
        CreateReportDto: {
            /**
             * Description
             * @description 설명. 받은 그대로 저장한다. 적지 않거나 null 이면 설명이 없는 것이다
             */
            description?: string | null;
            /**
             * Reason
             * @description 사유
             * @enum {string}
             */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
        };
        /**
         * HandleReportsDto
         * @description 운영자가 신고를 처리할 때 받는 값.
         */
        HandleReportsDto: {
            /**
             * Outcome
             * @description 처리한 결과. 조치함(actioned), 문제없음(dismissed)
             * @enum {string}
             */
            outcome: "actioned" | "dismissed";
        };
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /** InputError */
        InputError: {
            /** @description 무엇이 잘못됐는가. 화면에 그대로 보여 줄 수 있는 문장이다 */
            detail: string;
            /** @description 칸의 이름(점으로 이은 경로)마다 틀린 까닭들이다 */
            errors: {
                [key: string]: string[];
            };
        };
        /**
         * MeResponse
         * @description 토큰의 주인.
         */
        MeResponse: {
            /** Is Operator */
            is_operator: boolean;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * OpenReportGroupPageResponse
         * @description 열린 신고 목록의 한 쪽.
         */
        OpenReportGroupPageResponse: {
            /** Items */
            items: components["schemas"]["OpenReportGroupResponse"][];
            /**
             * Page
             * @description 몇 번째 쪽인가. 1 부터 센다
             */
            page: number;
            /**
             * Size
             * @description 한 쪽에 몇 개를 담는가
             */
            size: number;
            /**
             * Total
             * @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다
             */
            total: number;
        };
        /**
         * OpenReportGroupResponse
         * @description 운영자의 목록 한 줄. 신고당한 것 하나에 걸린 열린 신고들이다.
         */
        OpenReportGroupResponse: {
            /** First Reported At */
            first_reported_at: string;
            /** Last Reported At */
            last_reported_at: string;
            /** Open Count */
            open_count: number;
            reasons: components["schemas"]["ReasonCountsResponse"];
            target: components["schemas"]["ReportTargetResponse"];
        };
        /**
         * PinPostDto
         * @description 글을 고정할 때 받는 값. 본문 없이 불러도 된다.
         */
        PinPostDto: {
            /**
             * Days
             * @description 며칠 동안 고정하는가. 적지 않으면 7일이다. 그날이 지나면 저절로 내려간다
             * @default 7
             */
            days: number;
        };
        /**
         * PostListResponse
         * @description 게시판의 글 목록의 한 쪽. 고정한 글을 따로 싣는다.
         */
        PostListResponse: {
            /** Items */
            items: components["schemas"]["PostSummaryResponse"][];
            /**
             * Page
             * @description 몇 번째 쪽인가. 1 부터 센다
             */
            page: number;
            /**
             * Pinned
             * @description 지금 고정되어 있는 글들. 나중에 고정한 것부터다. 첫 쪽에만 싣는다. items 와 total 에는 들지 않는다
             */
            pinned: components["schemas"]["PostSummaryResponse"][];
            /**
             * Size
             * @description 한 쪽에 몇 개를 담는가
             */
            size: number;
            /**
             * Total
             * @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다
             */
            total: number;
        };
        /**
         * PostResponse
         * @description 글 하나. 목록의 한 줄에 본문이 더해진다.
         */
        PostResponse: {
            /**
             * Author Id
             * @description 글쓴이. 탈퇴한 사람이면 null 이다
             */
            author_id: string | null;
            /**
             * Author Nickname
             * @description 글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이거나 탈퇴한 사람이면 null 이다
             */
            author_nickname: string | null;
            /**
             * Author Withdrawn
             * @description 글쓴이가 탈퇴했는가
             */
            author_withdrawn: boolean;
            /**
             * Board
             * @description 글이 있는 게시판의 주소 이름(slug)
             */
            board: string;
            /**
             * Comment Count
             * @description 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다
             */
            comment_count: number;
            /** Content */
            content: string;
            /** Created At */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Pinned
             * @description 지금 고정되어 있는가
             */
            pinned: boolean;
            /**
             * Pinned Until
             * @description 고정이 끝나는 시각. 고정되어 있지 않으면 null 이다
             */
            pinned_until: string | null;
            /** Title */
            title: string;
            /** Updated At */
            updated_at: string;
        };
        /**
         * PostSummaryPageResponse
         * @description 글 목록의 한 쪽. 검색의 결과가 이 모양이다.
         */
        PostSummaryPageResponse: {
            /** Items */
            items: components["schemas"]["PostSummaryResponse"][];
            /**
             * Page
             * @description 몇 번째 쪽인가. 1 부터 센다
             */
            page: number;
            /**
             * Size
             * @description 한 쪽에 몇 개를 담는가
             */
            size: number;
            /**
             * Total
             * @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다
             */
            total: number;
        };
        /**
         * PostSummaryResponse
         * @description 글 목록의 한 줄.
         */
        PostSummaryResponse: {
            /**
             * Author Id
             * @description 글쓴이. 탈퇴한 사람이면 null 이다
             */
            author_id: string | null;
            /**
             * Author Nickname
             * @description 글쓴이의 닉네임. 이 서버가 이름을 모르는 사람이거나 탈퇴한 사람이면 null 이다
             */
            author_nickname: string | null;
            /**
             * Author Withdrawn
             * @description 글쓴이가 탈퇴했는가
             */
            author_withdrawn: boolean;
            /**
             * Board
             * @description 글이 있는 게시판의 주소 이름(slug)
             */
            board: string;
            /**
             * Comment Count
             * @description 살아 있는 댓글과 답글의 수. 지운 것은 세지 않는다
             */
            comment_count: number;
            /** Created At */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Pinned
             * @description 지금 고정되어 있는가
             */
            pinned: boolean;
            /**
             * Pinned Until
             * @description 고정이 끝나는 시각. 고정되어 있지 않으면 null 이다
             */
            pinned_until: string | null;
            /** Title */
            title: string;
            /** Updated At */
            updated_at: string;
        };
        /**
         * ReasonCountsResponse
         * @description 사유마다의 건수. 사유가 없었던 것도 0 으로 실린다.
         */
        ReasonCountsResponse: {
            /** Abuse */
            abuse: number;
            /** Illegal */
            illegal: number;
            /** Other */
            other: number;
            /** Sexual */
            sexual: number;
            /** Spam */
            spam: number;
        };
        /**
         * ReportPageResponse
         * @description 한 글이나 댓글에 걸린 신고 목록의 한 쪽.
         */
        ReportPageResponse: {
            /** Items */
            items: components["schemas"]["ReportResponse"][];
            /**
             * Page
             * @description 몇 번째 쪽인가. 1 부터 센다
             */
            page: number;
            /**
             * Size
             * @description 한 쪽에 몇 개를 담는가
             */
            size: number;
            /**
             * Total
             * @description 전체가 몇 개인가. 화면이 쪽의 수를 셈하는 데 쓴다
             */
            total: number;
        };
        /**
         * ReportReceiptResponse
         * @description 신고한 사람에게 돌려주는 것. 접수했다는 표시다.
         */
        ReportReceiptResponse: {
            /** Created At */
            created_at: string;
            /** Id */
            id: string;
            /**
             * Reason
             * @enum {string}
             */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
        };
        /**
         * ReportResponse
         * @description 운영자가 읽는 신고 한 건.
         */
        ReportResponse: {
            /** Created At */
            created_at: string;
            /**
             * Description
             * @description 신고한 사람이 붙인 설명. 적지 않았으면 null
             */
            description: string | null;
            /**
             * Handled At
             * @description 처리한 시각. 열린 신고면 null
             */
            handled_at: string | null;
            /**
             * Handled By
             * @description 처리한 운영자. 열린 신고면 null
             */
            handled_by: string | null;
            /** Id */
            id: string;
            /**
             * Outcome
             * @description 처리한 결과. 열린 신고면 null
             */
            outcome: ("actioned" | "dismissed") | null;
            /**
             * Reason
             * @enum {string}
             */
            reason: "spam" | "abuse" | "sexual" | "illegal" | "other";
            /**
             * Reporter Id
             * @description 신고한 사람. 인증 서버의 public_id. 탈퇴한 사람이면 null 이다
             */
            reporter_id: string | null;
        };
        /**
         * ReportTargetResponse
         * @description 신고당한 것. 운영자의 목록에서 무엇에 걸린 신고인지 보여 준다.
         */
        ReportTargetResponse: {
            /**
             * Deleted
             * @description 지금 지워져 있는가. 지운 것에 걸린 신고도 처리해서 닫아야 목록에서 빠진다
             */
            deleted: boolean;
            /** Id */
            id: string;
            /**
             * Post Id
             * @description 글이면 그 글의 번호, 댓글이면 그 댓글이 달린 글의 번호
             */
            post_id: string;
            /**
             * Type
             * @enum {string}
             */
            type: "post" | "comment";
        };
        /**
         * UpdateCommentDto
         * @description 댓글을 고칠 때 받는 값. 고칠 수 있는 것은 내용뿐이다. 어느 글, 어느 댓글에 달린 것인지는 옮길 수 없다.
         */
        UpdateCommentDto: {
            /** Content */
            content: string;
        };
        /**
         * UpdatePostDto
         * @description 글을 고칠 때 받는 값. 고칠 칸만 보낸다. 보내지 않은 칸은 그대로 둔다. 칸마다의 규칙은 쓸 때와 같다.
         *
         *     null 을 보낸 칸은 보낸 칸으로 치지만 고치지 않는다(NestJS 로 쓰던 때와 같다).
         */
        UpdatePostDto: {
            /** Content */
            content?: string | null;
            /** Title */
            title?: string | null;
        };
        /**
         * WithdrawalDto
         * @description 인증 서버가 보내는 탈퇴의 알림.
         */
        WithdrawalDto: {
            /**
             * Withdrawn At
             * @description 인증 서버가 계정을 비운 시각(ISO 8601, 시간대 포함)
             */
            withdrawn_at: string;
        };
        /**
         * WithdrawalResponse
         * @description 탈퇴를 받은 답. 인증 서버는 processed 를 받아야 보내기를 멈춘다.
         */
        WithdrawalResponse: {
            /**
             * Status
             * @description 반영했다. 이미 했거나 할 것이 없었던 것도 같다
             * @constant
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
    list_boards_api_v1_board_boards_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BoardResponse"][];
                };
            };
        };
    };
    list_posts_api_v1_board_boards__slug__posts_get: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostListResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    create_post_api_v1_board_boards__slug__posts_post: {
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
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    delete_comment_api_v1_board_comments__id__delete: {
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
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    update_comment_api_v1_board_comments__id__patch: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_comment_reports_api_v1_board_comments__id__reports_get: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportPageResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    report_comment_api_v1_board_comments__id__reports_post: {
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
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReceiptResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    handle_comment_reports_api_v1_board_comments__id__reports_outcome_put: {
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
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_me_api_v1_board_me_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MeResponse"];
                };
            };
        };
    };
    search_posts_api_v1_board_posts_get: {
        parameters: {
            query: {
                /** @description 몇 번째 쪽인가. 1 부터 센다 */
                page?: number;
                /** @description 한 쪽에 몇 개를 담는가 */
                size?: number;
                /** @description 검색어. 빈칸으로 낱말을 나눈다. 모든 낱말이 제목이나 본문에 들어 있는 글을 찾는다 */
                q: string;
                /** @description 어느 게시판에서 찾는가. 주소 이름(slug)이다. 적지 않으면 모든 게시판에서 찾는다 */
                board?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostSummaryPageResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_post_api_v1_board_posts__id__get: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    delete_post_api_v1_board_posts__id__delete: {
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
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    update_post_api_v1_board_posts__id__patch: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    pin_post_api_v1_board_posts__id__pin_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                id: string;
            };
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["PinPostDto"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    unpin_post_api_v1_board_posts__id__pin_delete: {
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
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_post_reports_api_v1_board_posts__id__reports_get: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportPageResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    report_post_api_v1_board_posts__id__reports_post: {
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
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReceiptResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    handle_post_reports_api_v1_board_posts__id__reports_outcome_put: {
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
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_comments_api_v1_board_posts__postId__comments_get: {
        parameters: {
            query?: {
                /** @description 이 번호의 댓글 다음부터 읽는다. 적지 않으면 처음부터다. 앞의 응답의 next 를 그대로 넣는다 */
                after?: string | null;
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentListResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    create_comment_api_v1_board_posts__postId__comments_post: {
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
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CommentResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_open_reports_api_v1_board_reports_get: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpenReportGroupPageResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    receive_api_v1_board_service_users__userId__withdrawal_post: {
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
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WithdrawalResponse"];
                };
            };
            /** @description 입력이 틀렸다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    check_health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
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
    check_readiness_health_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
}
