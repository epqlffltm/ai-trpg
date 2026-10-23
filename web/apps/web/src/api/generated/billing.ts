// web/apps/web/src/api/generated/billing.ts
// docs/api/billing.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/billing/attendance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 오늘의 출석. 본인인증 전이면 verified 가 false */
        get: operations["getAttendance"];
        put?: never;
        /** 오늘의 출석 보상을 받는다 */
        post: operations["claimAttendance"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/attendance/rewards": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 하루 양과 보물 상자의 확률. 로그인 없이 누구나 본다 */
        get: operations["getAttendanceRewards"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 토큰의 주인(인증 서버의 public_id) */
        get: operations["getMe"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 토큰의 주인의 주문. 만든 시각이 늦은 것부터 */
        get: operations["listOrders"];
        put?: never;
        /** 주문을 만든다. 같은 Idempotency-Key 로 다시 보내면 먼저 만든 주문을 200 으로 돌려준다 */
        post: operations["createOrder"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/orders/{id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 토큰의 주인의 주문 하나. 남의 주문이나 모양이 틀린 번호는 404 */
        get: operations["getOrder"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/orders/{id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** 결제의 승인을 요청한다. 결과가 났으면 200, 아직 모르면 202. 본문의 status 가 지금의 상태다 */
        post: operations["confirmOrder"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/orders/{id}/refund": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** 청약철회. 치른 지 7일 안이고 그 주문의 크레딧이 하나도 줄지 않았으면 전액을 취소한다 */
        post: operations["refundOrder"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 파는 상품 */
        get: operations["listProducts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/eligibility": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** (인증 서버) 사용자의 결제 자격(성년이 되는 날, 보호자 동의)을 받아 적는다. 가진 것보다 높은 버전만 받는다 */
        post: operations["recordEligibility"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/grants/welcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** (인증 서버) 본인인증을 마친 사용자에게 환영 크레딧을 준다. 한 사용자에 한 번 */
        post: operations["grantWelcome"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/holds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * (게임, chat 서버) 사용자의 크레딧을 먼저 빼 둔다. 같은 이름표로 다시 부르면 먼저 건 홀드를 200 으로 돌려준다
         * @description 서버마다 쓸 수 있는 가격표 이름의 머리가 있다(게임 narration, chat 의 chat 과 story). 다른 머리의 이름은 없는 가격표와 같은 400 price.unknown 이다
         */
        post: operations["placeHold"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/holds/capture": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** (게임, chat 서버) 홀드를 확정한다. 크레딧은 돌아오지 않는다. 그 서버가 건 홀드만 */
        post: operations["captureHold"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/holds/extend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** (게임, chat 서버) 홀드의 만료 시각을 지금부터 그 서버의 만료 시간(HOLD_TTL, chat 서버는 CHAT_HOLD_TTL) 뒤로 민다. 끝난 홀드면 409 */
        post: operations["extendHold"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/holds/release": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** (게임, chat 서버) 홀드를 돌려준다. 크레딧이 뺐던 자리로 돌아간다. 그 서버가 건 홀드만 */
        post: operations["releaseHold"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/prices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** (게임, chat 서버) 가격표의 지금 값과 다음에 바뀔 값. 부르는 서버의 머리의 줄만. If-None-Match 가 지금의 ETag 와 같으면 304 */
        get: operations["listPrices"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/service/users/{id}/withdrawal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * (인증 서버) 사용자의 탈퇴를 반영한다. 걸린 홀드를 돌려주고, 남은 크레딧을 소멸로 적고, 결제 자격을 지운다
         * @description 인증 서버가 유예(7일)가 지난 계정을 비운 뒤 알린다(docs/architecture/withdrawal.md). 200 과 processed 를 받을 때까지 다시 보낸다.
         *     몇 번을 받아도 결과가 같다. 이미 반영한 사용자와 이 서버가 모르는 사용자도 200 이다
         */
        post: operations["processWithdrawal"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/wallet": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 지금 쓸 수 있는 크레딧. 지갑이 없으면 모두 "0" 이다 */
        get: operations["getWallet"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/wallet/entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 원장. 최근 것부터 */
        get: operations["listWalletEntries"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/webhooks/payment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** 결제 대행사의 알림. 결과를 모르던 주문을 마저 끝낸다 */
        post: operations["paymentWebhook"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/billing/webhooks/toss": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 토스페이먼츠의 결제 상태 알림(PAYMENT_STATUS_CHANGED). PAYMENT_PROVIDER=toss 일 때만 있다
         * @description 서명이 없는 알림이다. 결과는 믿지 않고 토스페이먼츠에 다시 묻는다. 다른 종류의 알림도 200 이다.
         */
        post: operations["tossWebhook"];
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
        /** 프로세스가 살아 있다. DB 를 보지 않는다 */
        get: operations["health"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        /** GET 과 같다. 본문이 없다 */
        head: operations["healthHead"];
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
        /** DB 가 3초 안에 답하면 200, 아니면 503 */
        get: operations["ready"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        /** GET 과 같다. 본문이 없다 */
        head: operations["readyHead"];
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * @description 크레딧의 양. 정확한 값을 지키려고 숫자가 아니라 글자다
         * @example 80
         */
        Amount: string;
        AttendanceClaim: {
            /** @description 상자를 연 날이면 그 결과. 아니면 null */
            chest: {
                name: string;
                outcome: string;
                silver: components["schemas"]["Amount"];
                /** @description 확률표의 판 */
                table: string;
            } | null;
            cycle_day: number;
            /** Format: date */
            day: string;
            /**
             * Format: date-time
             * @description 받은 실버가 사라지는 때
             */
            expires_at: string;
            silver: components["schemas"]["Amount"];
        };
        AttendanceStatus: {
            /** @description 오늘 보물 상자를 여는 날인가 */
            chest: boolean;
            claimed: boolean;
            /** @description 오늘 받으면 주기의 며칠째인가(1부터) */
            cycle_day: number;
            cycle_length: number;
            silver: components["schemas"]["Amount"];
            /**
             * Format: date
             * @description 한국 날짜
             */
            today: string;
            /** @description 본인인증을 마쳤는가. 아니면 받을 수 없다 */
            verified: boolean;
        };
        Entries: {
            entries: components["schemas"]["Entry"][];
            /** @description 다음 쪽을 읽을 때 before 에 넣는다. 더 읽을 것이 없으면 null */
            next_before: string | null;
        };
        Entry: {
            amount: components["schemas"]["Amount"];
            /** Format: date-time */
            created_at: string;
            /** Format: uuid */
            hold_id: string | null;
            /** @enum {string|null} */
            hold_status: "held" | "captured" | "released" | null;
            /** @description 줄의 번호. 64비트 정수라 글자다 */
            id: string;
            /** @enum {string} */
            kind: "paid" | "free";
            /** Format: uuid */
            operation_id: string;
            /** Format: uuid */
            order_id: string | null;
            /** @enum {string} */
            reason: "deposit" | "grant" | "spend" | "expire" | "hold" | "release" | "regroup" | "refund" | "unrefund" | "forfeit";
        };
        Error: {
            /** @description 화면과 서버가 갈래를 나누는 오류의 이름(price.unknown 같은 것). 한번 정하면 바꾸지 않는다. 필요한 곳에만 있다 */
            code?: string;
            /** @description 사람이 읽는 글. 바뀔 수 있다 */
            detail: string;
        };
        Hold: {
            amount: components["schemas"]["Amount"];
            /** Format: date-time */
            created_at: string;
            /**
             * Format: date-time
             * @description 이때까지 확정하거나 연장하지 않으면 결제 서버가 돌려준다
             */
            expires_at: string;
            /** Format: uuid */
            id: string;
            price_code: string;
            reference: string;
            /** @enum {string|null} */
            release_reason: "requested" | "expired" | "withdrawn" | null;
            /** Format: date-time */
            settled_at: string | null;
            /** @enum {string} */
            status: "held" | "captured" | "released";
            /** Format: uuid */
            user_id: string;
        };
        Order: {
            /** Format: date-time */
            created_at: string;
            credits: components["schemas"]["Amount"];
            /**
             * Format: date-time
             * @description 이때까지 치르지 않으면 expired 가 된다
             */
            expires_at: string;
            /** @description 결제가 거절된 까닭(결제 대행사의 코드). failed 가 아니면 null */
            failure_code: string | null;
            /** Format: uuid */
            id: string;
            /** Format: date-time */
            paid_at: string | null;
            /**
             * Format: int64
             * @description 원
             */
            price: number;
            product_id: string;
            /**
             * @description 치른 주문인데 청약철회할 수 없는 까닭. 할 수 있거나 치른 주문이 아니면 null
             * @enum {string|null}
             */
            refund_blocked: "window_closed" | "credits_used" | null;
            /** @description 지금 청약철회를 할 수 있는가 */
            refundable: boolean;
            /** Format: date-time */
            refundable_until: string | null;
            /** Format: date-time */
            refunded_at: string | null;
            /** @enum {string} */
            status: "pending" | "confirming" | "paid" | "failed" | "expired" | "refunding" | "refunded";
        };
        PriceList: {
            prices: {
                /** @example narration.standard */
                code: string;
                /** @description 지금의 값. 판매를 멈췄으면 null */
                credits: components["schemas"]["Amount"] | null;
                /** @description 예약된 다음 값. 없으면 null */
                next: {
                    credits: components["schemas"]["Amount"] | null;
                    /** Format: date-time */
                    effective_at: string;
                    promo: boolean;
                    /** @enum {string|null} */
                    tier: "basic" | "standard" | "premium" | null;
                } | null;
                promo: boolean;
                /** Format: date-time */
                since: string | null;
                /** @enum {string|null} */
                tier: "basic" | "standard" | "premium" | null;
            }[];
        };
        Product: {
            credits: components["schemas"]["Amount"];
            id: string;
            name: string;
            /**
             * Format: int64
             * @description 원
             */
            price: number;
        };
        Rewards: {
            chest: {
                expected_silver: components["schemas"]["Amount"];
                outcomes: {
                    /** @description scale 가운데 몇 */
                    chance: number;
                    name: string;
                    outcome: string;
                    /** @example 5.0 */
                    percent: string;
                    silver: components["schemas"]["Amount"];
                }[];
                /** @description 확률의 분모 */
                scale: number;
                table: string;
            };
            cycle: {
                chest: boolean;
                day: number;
                silver: components["schemas"]["Amount"];
            }[];
        };
        Status: {
            /** @enum {string} */
            status: "ok" | "unavailable";
        };
        Wallet: {
            free: components["schemas"]["Amount"];
            /** @description 무료 크레딧 가운데 가장 먼저 사라지는 것. 없으면 null */
            next_expiry: {
                amount: components["schemas"]["Amount"];
                /** Format: date-time */
                expires_at: string;
            } | null;
            paid: components["schemas"]["Amount"];
            total: components["schemas"]["Amount"];
        };
        Welcome: {
            /** Format: date-time */
            expires_at: string | null;
            granted: components["schemas"]["Amount"];
            /** @enum {string} */
            status: "granted" | "already_granted" | "disabled";
        };
    };
    responses: {
        /** @description 요청의 값이 틀렸다. detail 이 무엇을 고칠지 말한다 */
        BadRequest: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 지금의 상태와 맞지 않는다(다른 내용으로 같은 열쇠를 썼다, 만료됐다 등). 같은 요청을 다시 보내도 같다 */
        Conflict: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 그런 것이 없다. 남의 것도 같은 답이다 */
        NotFound: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 결제할 수 없다. payment.verification_required(본인인증으로) 또는 payment.guardian_consent_required(보호자 동의로) */
        PaymentForbidden: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 받았다 */
        Received: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": {
                    received: boolean;
                };
            };
        };
        /** @description 서버 쪽의 문제다. 이유는 싣지 않는다 */
        ServerError: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /**
         * @description 요청을 받을 수 없다. code 가 까닭이다.
         *     service.bad_request(본문을 읽지 못했다), hold.invalid_request, price.unknown, price.not_for_sale,
         *     eligibility.invalid_request, withdrawal.invalid_request. 환영 크레딧의 user_id 가 없을 때는 code 가 없다
         */
        ServiceBadRequest: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description hold.reference_reused, hold.already_captured, hold.already_released */
        ServiceConflict: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 서명이 없거나 맞지 않다(service.bad_signature). 비밀과 시계를 확인한다 */
        ServiceUnauthorized: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 괜찮다 */
        StatusOK: {
            headers: {
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Status"];
            };
        };
        /** @description 토큰이 없거나 받아들일 수 없다. 이유는 싣지 않는다 */
        Unauthorized: {
            headers: {
                "WWW-Authenticate"?: string;
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 지금은 끝내지 못했다. 같은 요청을 다시 보낸다(DB 의 시간 제한, 요청의 마감, 공개키를 구할 수 없음) */
        Unavailable: {
            headers: {
                "Retry-After"?: number;
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        /** @description 주문 번호. 모양이 틀리면 없는 주문과 같은 404 다 */
        OrderID: string;
    };
    requestBodies: {
        HoldReference: {
            content: {
                "application/json": {
                    reference: string;
                };
            };
        };
    };
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    getAttendance: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 오늘 받았는지, 주기의 며칠째인지, 오늘의 양, 상자를 여는 날인지 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttendanceStatus"];
                };
            };
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    claimAttendance: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 받은 보상 */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AttendanceClaim"];
                };
            };
            401: components["responses"]["Unauthorized"];
            /** @description 본인인증 전이다(attendance.verification_required) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description 오늘 이미 받았다(attendance.already_claimed). 한국 자정에 다시 받는다 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    getAttendanceRewards: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 보상표 */
            200: {
                headers: {
                    "Cache-Control"?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Rewards"];
                };
            };
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    getMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 토큰의 주인 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** Format: uuid */
                        user_id: string;
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    listOrders: {
        parameters: {
            query?: {
                /** @description 이 주문보다 앞선 것만 읽는다. 앞 응답의 next_before 를 그대로 넣는다 */
                before?: string;
                /** @description 한 번에 읽는 주문 수(1~50, 기본 20) */
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 주문의 한 쪽 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /**
                         * Format: uuid
                         * @description 더 읽을 것이 없으면 null
                         */
                        next_before: string | null;
                        orders: components["schemas"]["Order"][];
                    };
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    createOrder: {
        parameters: {
            query?: never;
            header: {
                /** @description 같은 주문을 두 번 만들지 않게 하는 열쇠. 화면이 주문마다 새로 짓는다 */
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** @example credits-1000 */
                    product_id: string;
                };
            };
        };
        responses: {
            /** @description 같은 열쇠로 이미 만든 주문이다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            /** @description 새로 만들었다 */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["PaymentForbidden"];
            409: components["responses"]["Conflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    getOrder: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 주문 번호. 모양이 틀리면 없는 주문과 같은 404 다 */
                id: components["parameters"]["OrderID"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 주문 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    confirmOrder: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 주문 번호. 모양이 틀리면 없는 주문과 같은 404 다 */
                id: components["parameters"]["OrderID"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** @description 결제창이 준 결제 대행사의 결제 번호 */
                    payment_key: string;
                };
            };
        };
        responses: {
            /** @description 승인 또는 거절이 끝났다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            /** @description 결제 대행사의 답을 아직 모른다(confirming). 웹훅이나 대사가 마저 끝낸다 */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["PaymentForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    refundOrder: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 주문 번호. 모양이 틀리면 없는 주문과 같은 404 다 */
                id: components["parameters"]["OrderID"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 취소가 끝났다(refunded) */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            /** @description 결제 대행사의 답을 아직 모른다(refunding). 대사가 같은 취소를 다시 보낸다 */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Order"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["PaymentForbidden"];
            404: components["responses"]["NotFound"];
            /**
             * @description 청약철회를 할 수 없다. code 가 까닭이다.
             *     refund.window_closed(7일이 지났다), refund.credits_used(크레딧을 썼거나 홀드로 묶었다),
             *     refund.not_paid(치른 주문이 아니다), refund.busy(같은 주문의 다른 요청과 엇갈렸다. 다시 보낸다),
             *     refund.refused(결제 대행사가 거절했다. 크레딧은 돌아와 있다)
             */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    listProducts: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 상품의 목록 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        products: components["schemas"]["Product"][];
                    };
                };
            };
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    recordEligibility: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    guardian_consent: boolean;
                    /**
                     * Format: date
                     * @description 민법의 성년이 되는 날(만 19세 생일). 본인인증 전이면 null
                     */
                    legal_adult_from: string | null;
                    /** Format: uuid */
                    user_id: string;
                    /** Format: int64 */
                    version: number;
                };
            };
        };
        responses: {
            /** @description 적었다(applied) 또는 가진 것이 더 새것이라 적지 않았다(stale) */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        status: "applied" | "stale";
                    };
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    grantWelcome: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Format: uuid */
                    user_id: string;
                };
            };
        };
        responses: {
            /** @description 이미 줬다(already_granted) 또는 주지 않게 해 두었다(disabled) */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Welcome"];
                };
            };
            /** @description 줬다(granted) */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Welcome"];
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    placeHold: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** @example narration.standard */
                    price_code: string;
                    /** @description 부르는 서버가 지은 이름표(영문자, 숫자, 점, 밑줄, 쌍점, 붙임표로 된 8~200자) */
                    reference: string;
                    /** Format: uuid */
                    user_id: string;
                };
            };
        };
        responses: {
            /** @description 같은 이름표로 이미 건 홀드다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Hold"];
                };
            };
            /** @description 새로 걸었다 */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Hold"];
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            /** @description 크레딧이 모자란다. credit.insufficient 또는 credit.gold_required(프리미엄은 골드로만) */
            402: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            409: components["responses"]["ServiceConflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    captureHold: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: components["requestBodies"]["HoldReference"];
        responses: {
            /** @description 끝난 뒤의 홀드 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Hold"];
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            /** @description 그 이름표의 홀드가 없다(hold.not_found). 402 로 걸리지 않은 것도 여기다 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            409: components["responses"]["ServiceConflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    extendHold: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: components["requestBodies"]["HoldReference"];
        responses: {
            /** @description 끝난 뒤의 홀드 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Hold"];
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            /** @description 그 이름표의 홀드가 없다(hold.not_found). 402 로 걸리지 않은 것도 여기다 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            409: components["responses"]["ServiceConflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    releaseHold: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: components["requestBodies"]["HoldReference"];
        responses: {
            /** @description 끝난 뒤의 홀드 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Hold"];
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            /** @description 그 이름표의 홀드가 없다(hold.not_found). 402 로 걸리지 않은 것도 여기다 */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            409: components["responses"]["ServiceConflict"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    listPrices: {
        parameters: {
            query?: never;
            header?: {
                "If-None-Match"?: string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 가격 목록 */
            200: {
                headers: {
                    "Cache-Control"?: string;
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PriceList"];
                };
            };
            /** @description 바뀌지 않았다 */
            304: {
                headers: {
                    ETag?: string;
                    [name: string]: unknown;
                };
                content?: never;
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    processWithdrawal: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 탈퇴한 사용자(인증 서버의 public_id) */
                id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /**
                     * Format: date-time
                     * @description 인증 서버가 계정을 비운 시각
                     */
                    withdrawn_at: string;
                };
            };
        };
        responses: {
            /** @description 반영했다. 이미 했거나 할 것이 없었던 것도 같다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        status: "processed";
                    };
                };
            };
            400: components["responses"]["ServiceBadRequest"];
            401: components["responses"]["ServiceUnauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    getWallet: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 산 것(골드), 무료(실버), 둘의 합, 무료 중 가장 먼저 사라지는 것 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Wallet"];
                };
            };
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    listWalletEntries: {
        parameters: {
            query?: {
                /** @description 이 번호보다 앞선 줄만 읽는다. 앞 응답의 next_before 를 그대로 넣는다 */
                before?: string;
                /** @description 한 번에 읽는 줄 수(1~100, 기본 20) */
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 원장의 한 쪽 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Entries"];
                };
            };
            400: components["responses"]["BadRequest"];
            401: components["responses"]["Unauthorized"];
            500: components["responses"]["ServerError"];
            503: components["responses"]["Unavailable"];
        };
    };
    paymentWebhook: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": {
                    /** Format: uuid */
                    order_id: string;
                    payment_key: string;
                };
            };
        };
        responses: {
            200: components["responses"]["Received"];
            400: components["responses"]["BadRequest"];
            /** @description 서명이 없거나 맞지 않다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            500: components["responses"]["ServerError"];
            /** @description 지금은 처리할 수 없다. 결제 대행사가 다시 보낸다 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    tossWebhook: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": Record<string, never>;
            };
        };
        responses: {
            200: components["responses"]["Received"];
            400: components["responses"]["BadRequest"];
            500: components["responses"]["ServerError"];
            /** @description 토스페이먼츠에 묻지 못했다. 토스페이먼츠가 다시 보낸다 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    health: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: components["responses"]["StatusOK"];
            500: components["responses"]["ServerError"];
        };
    };
    healthHead: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 살아 있다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 서버 쪽의 문제다 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    ready: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            200: components["responses"]["StatusOK"];
            500: components["responses"]["ServerError"];
            /** @description DB 에 닿지 않는다. 이유는 싣지 않는다 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Status"];
                };
            };
        };
    };
    readyHead: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 요청을 받을 수 있다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 서버 쪽의 문제다 */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description DB 에 닿지 않는다 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
}
