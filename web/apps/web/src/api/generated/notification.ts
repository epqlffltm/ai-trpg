// web/apps/web/src/api/generated/notification.ts
// docs/api/notification.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/notification/me/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Notifications
         * @description 내 알림을 최근 것부터 읽는다. 다음 쪽은 받은 next_before 를 before 로 넘긴다.
         */
        get: operations["list_notifications_api_v1_notification_me_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/me/notifications/mutes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Mutes
         * @description 끌 수 있는 종류마다 껐는지 읽는다.
         */
        get: operations["read_mutes_api_v1_notification_me_notifications_mutes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/me/notifications/mutes/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Mute Kind
         * @description 그 종류를 끈다. 이미 꺼져 있어도 200 이다.
         */
        put: operations["mute_kind_api_v1_notification_me_notifications_mutes__kind__put"];
        post?: never;
        /**
         * Unmute Kind
         * @description 그 종류를 다시 켠다. 이미 켜져 있어도 200 이다.
         */
        delete: operations["unmute_kind_api_v1_notification_me_notifications_mutes__kind__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/me/notifications/read-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Read All
         * @description 번호 up_to 까지의 읽지 않은 알림을 모두 읽음으로 한다. 이번에 읽음이 된 수를 돌려준다.
         */
        post: operations["read_all_api_v1_notification_me_notifications_read_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/me/notifications/unread-count": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Count Unread
         * @description 읽지 않은 알림의 수. 화면의 종 모양 옆 숫자다.
         */
        get: operations["count_unread_api_v1_notification_me_notifications_unread_count_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/me/notifications/{notification_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Read One
         * @description 알림 하나를 읽음으로 한다. 이미 읽었으면 처음 읽은 시각 그대로 200 이다.
         */
        post: operations["read_one_api_v1_notification_me_notifications__notification_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/service/users/{user_id}/withdrawal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Receive Withdrawal
         * @description 그 사람의 알림과 끈 종류를 지운다. 지웠든, 이미 지웠든, 없던 사람이든 200 이다.
         */
        post: operations["receive_withdrawal_api_v1_notification_service_users__user_id__withdrawal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notification/service/{source}/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Put Notification
         * @description 알림 하나를 넣는다. 같은 알림을 다시 보내면 같은 id 로 200 이다. 받는 사람이 껐으면 적지 않고 200 이다.
         */
        post: operations["put_notification_api_v1_notification_service__source__notifications_post"];
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
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /**
         * KindMute
         * @description 끌 수 있는 종류 하나와 그것을 껐는지.
         */
        KindMute: {
            /** Kind */
            kind: string;
            /** Muted */
            muted: boolean;
        };
        /**
         * MuteSettings
         * @description 이 사람의 알림 끄기 설정. 끌 수 있는 종류 전부다(이름 차례). 끌 수 없는 종류는 싣지 않는다.
         *
         *     화면은 이것으로 켜고 끄는 단추를 그린다. 종류의 이름을 사람의 말로 바꾸는 것은 화면이 한다.
         */
        MuteSettings: {
            /** Kinds */
            kinds: components["schemas"]["KindMute"][];
        };
        /**
         * NotificationPage
         * @description 알림함의 한 쪽. 최근 것부터다.
         *
         *     next_before 가 있으면 그 값을 before 로 다시 부르면 다음 쪽이다. 없으면 끝이다.
         */
        NotificationPage: {
            /** Items */
            items: components["schemas"]["NotificationView"][];
            /** Next Before */
            next_before: number | null;
        };
        /**
         * NotificationPut
         * @description 넣기의 답. 넣는 서버는 이것을 받으면 발송함에서 그 줄을 지운다.
         */
        NotificationPut: {
            /** Id */
            id: number | null;
            status: components["schemas"]["PutStatus"];
        };
        /**
         * NotificationView
         * @description 알림함에 보이는 알림 하나. 넣은 서버가 붙인 열쇠(source_key)와 받는 사람은 싣지 않는다(내 것이다).
         */
        NotificationView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: number;
            /** Kind */
            kind: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Read At */
            read_at: string | null;
            /** Source */
            source: string;
        };
        /**
         * PutStatus
         * @description 넣기의 결과.
         * @enum {string}
         */
        PutStatus: "created" | "existing" | "muted";
        /**
         * ReadAllRequest
         * @description 모두 읽음. up_to 번호까지(그 번호 포함) 읽지 않은 알림을 읽음으로 한다.
         *
         *     화면이 마지막으로 받은 알림의 번호를 보낸다. "지금까지 전부"로 하면, 목록을 받은 뒤에 막 들어와
         *     화면에 보이지도 않은 알림까지 읽음이 된다.
         */
        ReadAllRequest: {
            /** Up To */
            up_to: number;
        };
        /**
         * ReadAllResult
         * @description 모두 읽음의 결과. 이번에 읽음이 된 알림의 수다.
         */
        ReadAllResult: {
            /** Read */
            read: number;
        };
        /**
         * UnreadCount
         * @description 읽지 않은 알림의 수.
         */
        UnreadCount: {
            /** Unread */
            unread: number;
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WithdrawalOut
         * @description 탈퇴를 받은 답. 지운 수는 싣지 않는다. 인증 서버는 결과만 본다.
         */
        WithdrawalOut: {
            status: components["schemas"]["WithdrawalStatus"];
        };
        /**
         * WithdrawalStatus
         * @description 탈퇴를 받은 결과. 인증 서버는 processed 를 받아야 보내기를 멈춘다.
         * @enum {string}
         */
        WithdrawalStatus: "processed";
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_notifications_api_v1_notification_me_notifications_get: {
        parameters: {
            query?: {
                before?: number | null;
                limit?: number;
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
                    "application/json": components["schemas"]["NotificationPage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_mutes_api_v1_notification_me_notifications_mutes_get: {
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
                    "application/json": components["schemas"]["MuteSettings"];
                };
            };
        };
    };
    mute_kind_api_v1_notification_me_notifications_mutes__kind__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kind: string;
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
                    "application/json": components["schemas"]["MuteSettings"];
                };
            };
            /** @description 끌 수 없거나 표에 없는 종류다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    unmute_kind_api_v1_notification_me_notifications_mutes__kind__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kind: string;
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
                    "application/json": components["schemas"]["MuteSettings"];
                };
            };
            /** @description 끌 수 없거나 표에 없는 종류다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    read_all_api_v1_notification_me_notifications_read_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReadAllRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReadAllResult"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    count_unread_api_v1_notification_me_notifications_unread_count_get: {
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
                    "application/json": components["schemas"]["UnreadCount"];
                };
            };
        };
    };
    read_one_api_v1_notification_me_notifications__notification_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notification_id: number;
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
                    "application/json": components["schemas"]["NotificationView"];
                };
            };
            /** @description 그런 알림이 없거나 남의 것이다 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    receive_withdrawal_api_v1_notification_service_users__user_id__withdrawal_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["WithdrawalOut"];
                };
            };
            /** @description 서명이 없거나 맞지 않다(AUTH_SERVER_SECRET) */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 본문이 16KB 를 넘는다 */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    put_notification_api_v1_notification_service__source__notifications_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                source: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 같은 알림을 다시 보냈다(existing). 받는 사람이 그 종류를 꺼서 적지 않았다(muted) */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationPut"];
                };
            };
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NotificationPut"];
                };
            };
            /** @description 서명이 없거나 맞지 않다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 같은 열쇠의 다른 알림이다 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 본문이 16KB 를 넘는다 */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
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
