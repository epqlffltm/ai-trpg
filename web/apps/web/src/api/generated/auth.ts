// web/apps/web/src/api/generated/auth.ts
// docs/api/auth.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/auth/consents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 동의를 받는 항목마다 지금의 판. 로그인 없이 읽는다
         * @description GET /api/v1/auth/consents. 동의를 받는 항목마다 지금의 판(#450). 가입 화면이 쓰므로 로그인 없이 읽는다.
         */
        get: operations["consents_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/guardian/consent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 보호자가 메일의 링크에서 본인인증을 하고 동의한다
         * @description POST /api/v1/auth/guardian/consent. 보호자가 메일의 링크에서 본인인증을 하고 동의한다.
         */
        post: operations["guardian_consent_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/guardian/request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 미성년자가 보호자에게 결제 동의를 부탁한다
         * @description POST /api/v1/auth/guardian/request. 미성년자가 보호자에게 결제 동의를 부탁한다(#336).
         */
        post: operations["guardian_request_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/guardian/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 보호자가 메일의 링크로 동의를 철회한다
         * @description POST /api/v1/auth/guardian/revoke. 보호자가 메일의 링크로 동의를 철회한다.
         */
        post: operations["guardian_revoke_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/identity/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 휴대폰 본인인증을 적는다
         * @description POST /api/v1/auth/identity/verify. 휴대폰 본인인증(#336).
         */
        post: operations["identity_verify_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/jwks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 토큰을 검증할 공개키(JWKS). 다른 서버가 받아 간다
         * @description GET /api/v1/auth/jwks
         */
        get: operations["jwks_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 로그인 1단계: 아이디와 비밀번호가 맞으면 메일로 코드를 보내고 티켓을 준다
         * @description POST /api/v1/auth/login
         */
        post: operations["login_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login/resend": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 로그인 코드를 다시 보낸다
         * @description POST /api/v1/auth/login/resend
         */
        post: operations["login_resend_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 로그인 2단계: 코드를 맞히면 토큰을 준다
         * @description POST /api/v1/auth/login/verify
         */
        post: operations["login_verify_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 이 기기에서 로그아웃한다. refresh 토큰을 폐기하고 쿠키를 지운다
         * @description POST /api/v1/auth/logout
         */
        post: operations["logout_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 모든 기기에서 로그아웃한다(세션 버전을 올린다)
         * @description POST /api/v1/auth/logout-all
         */
        post: operations["logout_all_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 로그인한 본인의 계정
         * @description GET /api/v1/auth/me
         */
        get: operations["me_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me/consents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 본인의 항목마다의 동의 상태
         * @description GET /api/v1/auth/me/consents. 본인의 항목마다의 동의 상태(#450).
         */
        get: operations["me_consents_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me/consents/{item}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * 그 항목에 동의한다(본문의 판으로)
         * @description PUT /api/v1/auth/me/consents/{item}: 그 항목에 동의한다(본문의 판으로).
         *     DELETE /api/v1/auth/me/consents/{item}: 그 항목의 동의를 철회한다. 필수 항목은 철회하지 못한다.
         */
        put: operations["me_consents_update"];
        post?: never;
        /**
         * 그 항목의 동의를 철회한다. 필수 항목은 철회하지 못한다
         * @description PUT /api/v1/auth/me/consents/{item}: 그 항목에 동의한다(본문의 판으로).
         *     DELETE /api/v1/auth/me/consents/{item}: 그 항목의 동의를 철회한다. 필수 항목은 철회하지 못한다.
         */
        delete: operations["me_consents_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/me/withdrawal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 탈퇴를 요청한다. 모든 세션이 끊기고 7일 뒤에 계정을 비운다. 그 안에 다시 로그인해 취소한다
         * @description POST, DELETE /api/v1/auth/me/withdrawal. 탈퇴를 요청하고 취소한다(#603, docs/architecture/withdrawal.md).
         */
        post: operations["me_withdrawal_create"];
        /**
         * 유예 중인 탈퇴를 취소한다. 그 뒤의 /refresh 부터 모든 서버에 통한다. 요청하지 않았어도 200
         * @description POST, DELETE /api/v1/auth/me/withdrawal. 탈퇴를 요청하고 취소한다(#603, docs/architecture/withdrawal.md).
         */
        delete: operations["me_withdrawal_destroy"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password/change": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 비밀번호를 바꾼다. 다른 기기는 로그아웃되고 이 기기는 새 토큰을 받는다
         * @description POST /api/v1/auth/password/change
         */
        post: operations["password_change_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password/reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 비밀번호 재설정 메일을 보낸다
         * @description POST /api/v1/auth/password/reset
         */
        post: operations["password_reset_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password/reset/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 메일의 링크로 비밀번호를 새로 정한다
         * @description POST /api/v1/auth/password/reset/confirm
         */
        post: operations["password_reset_confirm_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/public-names": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 다른 사람의 공개 ID 로 이름을 한꺼번에 찾는다. 로그인 없이 읽는다
         * @description GET /api/v1/auth/public-names?ids=<공개 ID>,<공개 ID>,... 다른 사람의 이름을 한꺼번에 찾는다(#532).
         *
         *     공개 목록은 로그인 없이 읽으므로(#530) 이것도 로그인 없이 연다. 닉네임만 나간다(accounts/public_names.py).
         */
        get: operations["public_names_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * refresh 쿠키로 새 access 토큰을 받는다. refresh 토큰도 새것으로 바뀐다
         * @description POST /api/v1/auth/refresh
         */
        post: operations["refresh_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/service/guardian-notices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 결제 서버가 미성년자의 결제와 청약철회를 알린다(서버끼리)
         * @description POST /api/v1/auth/service/guardian-notices. 결제 서버가 미성년자의 결제와 청약철회를 알린다(#352).
         */
        post: operations["service_guardian_notices_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/session-revocations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 끊긴 세션의 목록. 다른 서버가 30초마다 받아 간다
         * @description GET /api/v1/auth/session-revocations
         */
        get: operations["session_revocations_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/signup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 가입 1단계: 이메일로 코드를 보낸다
         * @description POST /api/v1/auth/signup. 가입의 1단계: 이메일로 코드를 보낸다. 다시 보낼 때도 이것이다.
         */
        post: operations["signup_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/signup/complete": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 가입 3단계: 티켓과 가입 내용으로 계정을 만든다
         * @description POST /api/v1/auth/signup/complete. 가입의 3단계: 티켓과 가입 내용으로 계정을 만든다.
         */
        post: operations["signup_complete_create"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/signup/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 가입 2단계: 코드를 맞히면 가입 티켓을 준다
         * @description POST /api/v1/auth/signup/verify. 가입의 2단계: 코드를 확인하고 가입 티켓을 준다.
         */
        post: operations["signup_verify_create"];
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
        /** DB 에 닿으면 200, 아니면 503 */
        get: operations["ready"];
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
         * @description access 토큰이 없거나 받아들일 수 없을 때(401). DRF 와 simplejwt 가 만든다.
         *
         *     토큰이 틀렸으면 code(token_not_valid)와 messages 가 붙는다. 화면은 이유를 가르지 않고 갱신하거나 다시 로그인한다.
         */
        AuthError: {
            code?: string;
            detail: string;
            messages?: {
                [key: string]: unknown;
            }[];
        };
        /** @description 화면이 가를 수 있게 오류의 이름(code)을 싣는 거절. */
        CodedError: {
            code: string;
            detail: string;
        };
        /** @description 항목 하나에 동의한다. 화면이 보인 문서의 판을 보낸다. */
        ConsentAgreeRequest: {
            version: number;
        };
        /** @description 동의를 받는 항목 하나의 지금의 판. 화면이 가입과 설정에서 보일 문서를 고른다. */
        ConsentDocument: {
            /** Format: date */
            effective_on: string;
            item: string;
            required: boolean;
            version: number;
        };
        ConsentDocuments: {
            items: components["schemas"]["ConsentDocument"][];
        };
        /** @description 본인의 항목 하나의 동의 상태. 동의하지 않았거나 철회했으면 agreed_version 과 agreed_at 이 null 이다. */
        ConsentState: {
            /** Format: date-time */
            agreed_at: string | null;
            agreed_version: number | null;
            item: string;
            pending: boolean;
            required: boolean;
            version: number;
        };
        ConsentStates: {
            items: components["schemas"]["ConsentState"][];
        };
        /** @description 글 하나만 싣는 응답. 성공의 안내도, 이유를 가르지 않는 거절도 이 모양이다. */
        Detail: {
            detail: string;
        };
        /** @description 이메일 주소 하나만 받는 요청. 가입의 1단계(코드 보내기와 다시 보내기)와 비밀번호 재설정 요청에 쓴다. */
        EmailRequest: {
            /** Format: email */
            email: string;
        };
        /** @description 보호자의 동의. 메일의 동의 링크에서 꺼낸 글자와, 보호자가 본인확인 업체에서 받은 글자를 받는다. */
        GuardianConsentRequest: {
            consent_token: string;
            identity_token: string;
        };
        /** @description 결제 서버에 주는 답. queued(메일을 적었다), skipped(알릴 보호자가 없다), duplicate(이미 받았다). */
        GuardianNoticeAnswer: {
            status: components["schemas"]["StatusEnum"];
        };
        /** @description 결제 서버가 보낸 보호자 알림(#352). 본문의 모양만 본다. 서명은 뷰가 먼저 본다. */
        GuardianNoticeRequest: {
            credits: number;
            kind: components["schemas"]["KindEnum"];
            /** Format: date-time */
            occurred_at: string;
            /** Format: uuid */
            order_id: string;
            price: number;
            product_id: string;
            /** Format: uuid */
            user_id: string;
        };
        /** @description 보호자에게 동의를 부탁한다. 보호자의 이메일 하나를 받는다. */
        GuardianRequestRequest: {
            /** Format: email */
            guardian_email: string;
        };
        /** @description 보호자에게 동의 요청 메일을 보냈다. */
        GuardianRequested: {
            detail: string;
            guardian_consent: components["schemas"]["GuardianRequestedGuardianConsentEnum"];
        };
        /**
         * @description * `requested` - requested
         * @enum {string}
         */
        GuardianRequestedGuardianConsentEnum: "requested";
        /** @description 보호자의 철회. 메일의 철회 링크에서 꺼낸 글자를 받는다. */
        GuardianRevokeRequest: {
            revoke_token: string;
        };
        /** @description 보호자가 철회했다. revoked 는 이번 요청이 철회했는지다(이미 철회된 링크면 false). */
        GuardianRevoked: {
            detail: string;
            revoked: boolean;
        };
        /** @description 본인인증을 마친 뒤의 상태. */
        IdentityAnswer: {
            identity: components["schemas"]["IdentityStatus"];
        };
        /** @description 본인인증 상태(identity_status.IdentityStatus). 내 정보와 본인인증의 응답에 실린다. */
        IdentityStatus: {
            adult_content: boolean;
            legal_adult: boolean;
            verified: boolean;
        };
        /** @description 본인인증. 본인확인 업체의 화면에서 받은 글자 하나를 받는다. 모양은 업체가 정한다(identity_providers.py). */
        IdentityVerifyRequest: {
            token: string;
        };
        /** @description 공개키 하나(RFC 7517). 토큰 머리말의 kid 로 고른다. */
        Jwk: {
            alg: string;
            e: string;
            key_ops: string[];
            kid: string;
            kty: string;
            n: string;
            use: string;
        };
        /** @description 검증할 수 있는 공개키 모두. 서명 키가 맨 앞이다. 키를 바꾸는 동안에는 옛 키도 실린다. */
        Jwks: {
            keys: components["schemas"]["Jwk"][];
        };
        /**
         * @description * `paid` - 결제
         *     * `refunded` - 청약철회
         * @enum {string}
         */
        KindEnum: "paid" | "refunded";
        /** @description 로그인 1단계 응답. 토큰이 아니라 다음 단계에 쓸 티켓을 준다. */
        LoginChallenge: {
            detail: string;
            login_ticket: string;
        };
        /**
         * @description 로그인 요청을 검증한다.
         *
         *     형식만 본다. 아이디 규칙이나 비밀번호 강도는 검사하지 않는다.
         *     규칙에 어긋난 입력에 다른 오류를 주면 "이런 아이디는 존재할 수 없다" 를 알려 주게 된다.
         */
        LoginRequest: {
            password: string;
            username: string;
        };
        /**
         * @description 토큰을 발급하는 응답. 로그인 2단계, 토큰 갱신, 비밀번호 변경이 쓴다.
         *
         *     consents_pending 이 비어 있지 않으면 다시 동의할 필수 항목이 남았다(#450). 그 access 토큰은 인증 서버에만 통한다.
         *     화면은 동의를 받은 뒤(PUT /me/consents/<항목>) /refresh 로 모든 서버에 통하는 토큰을 받는다.
         */
        LoginResponse: {
            access_token: string;
            /** @description 다시 동의할 필수 항목. 비어 있지 않으면 access 토큰이 인증 서버에만 통한다 */
            consents_pending: string[];
            expires_in: number;
            token_type: string;
            /**
             * Format: date-time
             * @description 탈퇴를 요청했으면 계정을 비울 시각(#603). 있으면 access 토큰이 인증 서버에만 통한다. 취소하면 null
             */
            withdrawal_scheduled_at: string | null;
        };
        /** @description 로그인 티켓 하나만 받는 요청. 로그인 코드 재발송에 쓴다. */
        LoginTicketRequest: {
            login_ticket: string;
        };
        /** @description 로그인 2단계 요청을 검증한다. */
        LoginVerifyRequest: {
            code: string;
            login_ticket: string;
        };
        /** @description GET /me 의 응답. 계정 정보에 본인인증, 보호자 동의, 다시 받을 동의, 탈퇴의 상태를 더한다. */
        Me: {
            consents_pending: string[];
            /**
             * 이메일
             * Format: email
             */
            readonly email: string;
            guardian_consent: components["schemas"]["MeGuardianConsentEnum"];
            identity: components["schemas"]["IdentityStatus"];
            /** 닉네임 */
            readonly nickname: string;
            /**
             * 공개 ID
             * Format: uuid
             */
            readonly public_id: string;
            /** 아이디 */
            readonly username: string;
            /** Format: date-time */
            withdrawal_scheduled_at: string | null;
        };
        /**
         * @description * `none` - none
         *     * `requested` - requested
         *     * `consented` - consented
         *     * `revoked` - revoked
         * @enum {string}
         */
        MeGuardianConsentEnum: "none" | "requested" | "consented" | "revoked";
        /**
         * @description 비밀번호 변경 요청의 형식을 검증한다.
         *
         *     새 비밀번호의 강도는 여기서 보지 않는다. services.py 가 사용자와 함께 검사한다.
         */
        PasswordChangeRequest: {
            current_password: string;
            new_password: string;
        };
        /** @description 비밀번호 재설정 요청의 형식을 검증한다. */
        PasswordResetConfirmRequest: {
            /** Format: email */
            email: string;
            new_password: string;
            token: string;
        };
        /** @description 다른 사람의 공개 ID 와 이름. 없거나 막은 계정이면 nickname 이 null 이다. */
        PublicName: {
            nickname: string | null;
            /** Format: uuid */
            public_id: string;
        };
        PublicNames: {
            names: components["schemas"]["PublicName"][];
        };
        /** @description 시도가 너무 많거나 메일을 지금은 보낼 수 없을 때(429). retry_after 초 뒤에는 된다. Retry-After 머리말도 같다. */
        RetryLater: {
            code: string;
            detail: string;
            retry_after: number;
        };
        /** @description 끊긴 세션 하나. sub 의 SHA-256(16진수)과, 그보다 낮으면 거부할 세션 버전. */
        Revocation: {
            min_ver: number;
            sub_sha256: string;
        };
        /** @description 끊긴 세션의 목록(#274). 받는 서버는 refresh_interval_seconds 마다 다시 받는다. */
        RevocationDocument: {
            refresh_interval_seconds: number;
            revocations: components["schemas"]["Revocation"][];
        };
        /**
         * @description 가입의 3단계. 가입 티켓과 가입 내용의 형식을 검증한다.
         *
         *     티켓이 맞는지, 아이디가 이메일과 겹치는지, 비밀번호가 강한지는 여기서 보지 않는다.
         *     셋 다 티켓 속의 이메일이 있어야 판단할 수 있어서 services.py 가 티켓을 읽은 뒤에 본다.
         *     중복도 services.py 가 본다.
         */
        SignupCompleteRequest: {
            age_over_14: boolean;
            consents: {
                [key: string]: number;
            };
            nickname: string;
            password: string;
            signup_ticket: string;
            username: string;
        };
        /** @description 가입의 1단계. 이메일만 받는다. 아이디와 비밀번호는 코드를 맞힌 뒤에 받는다(#271). */
        SignupRequest: {
            /** Format: email */
            email: string;
        };
        /** @description 가입 2단계의 응답. 3단계에 쓸 가입 티켓을 준다. */
        SignupVerified: {
            detail: string;
            signup_ticket: string;
        };
        /** @description 가입 인증 요청을 검증한다. */
        SignupVerifyRequest: {
            code: string;
            /** Format: email */
            email: string;
        };
        /**
         * @description * `queued` - queued
         *     * `skipped` - skipped
         *     * `duplicate` - duplicate
         * @enum {string}
         */
        StatusEnum: "queued" | "skipped" | "duplicate";
        /** @description 탈퇴 요청(#603). 열린 채 둔 기기에서 남이 누르지 못하게 비밀번호를 다시 받는다. */
        WithdrawalRequestRequest: {
            password: string;
        };
        /** @description 탈퇴의 상태(#603). 요청하면 계정을 비울 시각, 취소하면 null 이다. */
        WithdrawalState: {
            /** Format: date-time */
            withdrawal_scheduled_at: string | null;
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
    consents_retrieve: {
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
                    "application/json": components["schemas"]["ConsentDocuments"];
                };
            };
        };
    };
    guardian_consent_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GuardianConsentRequest"];
            };
        };
        responses: {
            /** @description 동의를 적었다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 링크를 쓸 수 없다(guardian_link_invalid) 또는 본인인증의 글자를 쓸 수 없다(identity_token_invalid) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 보호자가 성년이 아니다(guardian_not_adult) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 회원이 이미 성년이다(guardian_not_needed) 또는 회원 본인이다(guardian_is_minor) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 본인확인 업체에 닿지 않는다(identity_unavailable) */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    guardian_request_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GuardianRequestRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GuardianRequested"];
                };
            };
            /** @description 형식이 틀렸거나 내 이메일을 적었다(guardian_email) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 본인인증을 먼저 한다(identity_verification_required) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 성년이다(guardian_not_needed) 또는 보호자가 이미 동의했다(guardian_consent_active) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 보호자에게 너무 자주 요청했다(guardian_request_unavailable) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    guardian_revoke_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GuardianRevokeRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GuardianRevoked"];
                };
            };
            /** @description 링크를 쓸 수 없다(guardian_link_invalid) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
        };
    };
    identity_verify_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["IdentityVerifyRequest"];
            };
        };
        responses: {
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IdentityAnswer"];
                };
            };
            /** @description 형식이 틀렸거나 본인인증의 글자를 쓸 수 없다(identity_token_invalid) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 만 14세 미만이라 계정을 막았다(identity_under_age). refresh 쿠키도 지운다. 또는 정지된 채 탈퇴한 사람이라 인증하지 않았다(identity_blocked) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 이미 본인인증을 마쳤다(identity_already_verified) 또는 다른 계정이 쓴 사람이다(identity_in_use) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 본인확인 업체에 닿지 않는다(identity_unavailable) */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    jwks_retrieve: {
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
                    "application/json": components["schemas"]["Jwks"];
                };
            };
        };
    };
    login_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginChallenge"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 아이디 또는 비밀번호가 틀렸다. 막힌 IP 에도 같은 답이다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 이메일 인증을 마치지 않았다(email_not_verified) 또는 막은 IP 다(network_blocked) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 시도가 너무 많다(too_many_attempts) 또는 코드를 자주 요청했다(login_code_unavailable) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    login_resend_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginTicketRequest"];
            };
        };
        responses: {
            /** @description 다시 보냈다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 로그인 티켓을 쓸 수 없다(login_ticket_invalid) */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 막은 IP 에서 온 요청(network_blocked). 기간이 지나면 풀린다 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 코드를 너무 자주 요청했다(login_code_unavailable) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    login_verify_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginVerifyRequest"];
            };
        };
        responses: {
            /** @description access 토큰. refresh 토큰은 쿠키다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description 형식이 틀렸거나 코드가 맞지 않거나 만료됐다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 로그인 티켓을 쓸 수 없다(login_ticket_invalid). 처음부터 다시 한다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 막은 IP 에서 온 요청(network_blocked). 기간이 지나면 풀린다 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    logout_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 로그아웃했다. 토큰이 없었어도 같다 */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 허용하지 않은 출처에서 온 쿠키 요청(origin_not_allowed) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    logout_all_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 모든 세션을 끊었다 */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
        };
    };
    me_retrieve: {
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
                    "application/json": components["schemas"]["Me"];
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
        };
    };
    me_consents_retrieve: {
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
                    "application/json": components["schemas"]["ConsentStates"];
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
        };
    };
    me_consents_update: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConsentAgreeRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConsentStates"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 그런 항목이 없다(consent_item_unknown) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 문서의 판이 바뀌었다(consent_outdated) */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    me_consents_destroy: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                item: string;
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
                    "application/json": components["schemas"]["ConsentStates"];
                };
            };
            /** @description 필수 항목이다(consent_required). 탈퇴로 한다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 그런 항목이 없다(consent_item_unknown) */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    me_withdrawal_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WithdrawalRequestRequest"];
            };
        };
        responses: {
            /** @description 받았다. 계정을 비울 시각 */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WithdrawalState"];
                };
            };
            /** @description 비밀번호가 틀렸다(password) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 시도가 너무 많다(too_many_attempts) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    me_withdrawal_destroy: {
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
                    "application/json": components["schemas"]["WithdrawalState"];
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
        };
    };
    password_change_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordChangeRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description 현재 비밀번호가 틀렸거나(current_password) 새 비밀번호가 규칙에 어긋났다(new_password) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description access 토큰이 없거나 받아들일 수 없다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuthError"];
                };
            };
            /** @description 시도가 너무 많다(too_many_attempts) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    password_reset_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EmailRequest"];
            };
        };
        responses: {
            /** @description 가입된 주소면 보냈다. 아니어도 같은 답이다 */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 시도가 너무 많다(too_many_attempts) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    password_reset_confirm_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetConfirmRequest"];
            };
        };
        responses: {
            /** @description 바꿨다. 새 비밀번호로 로그인한다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 링크가 틀렸거나 만료됐거나 새 비밀번호가 규칙에 어긋났다(new_password) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
        };
    };
    public_names_retrieve: {
        parameters: {
            query: {
                /** @description 공개 ID 를 쉼표로 이은 것(100개까지) */
                ids: string;
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
                    "application/json": components["schemas"]["PublicNames"];
                };
            };
            /** @description 공개 ID 의 목록이 틀렸다(public_ids_invalid) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    refresh_create: {
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
                    "application/json": components["schemas"]["LoginResponse"];
                };
            };
            /** @description refresh 쿠키가 없거나 쓸 수 없다. 다시 로그인한다 */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 허용하지 않은 출처의 쿠키 요청(origin_not_allowed) 또는 막은 IP 다(network_blocked) */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    service_guardian_notices_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["GuardianNoticeRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["GuardianNoticeAnswer"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 결제 서버의 서명이 맞지 않다(service_bad_signature) */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
        };
    };
    session_revocations_retrieve: {
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
                    "application/json": components["schemas"]["RevocationDocument"];
                };
            };
        };
    };
    signup_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupRequest"];
            };
        };
        responses: {
            /** @description 코드를 보냈다. 이미 가입된 주소여도 같은 답이다 */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 요청을 받을 수 없다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 막은 IP 에서 온 요청(network_blocked). 기간이 지나면 풀린다 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 시도가 너무 많다(too_many_attempts) */
            429: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RetryLater"];
                };
            };
        };
    };
    signup_complete_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupCompleteRequest"];
            };
        };
        responses: {
            /** @description 가입했다. 로그인은 따로 한다 */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Detail"];
                };
            };
            /** @description 칸의 오류이거나 티켓을 쓸 수 없다(signup_ticket_invalid) */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 막은 IP 에서 온 요청(network_blocked). 기간이 지나면 풀린다 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
                };
            };
            /** @description 이미 가입한 이메일(email_registered)이거나, 다른 가입이 같은 이름을 방금 가져갔다 */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
        };
    };
    signup_verify_create: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SignupVerifyRequest"];
            };
        };
        responses: {
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SignupVerified"];
                };
            };
            /** @description 형식이 틀렸거나 코드가 맞지 않거나 만료됐다 */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string[] | Record<string, never>;
                    } | {
                        code?: string;
                        detail: string;
                    };
                };
            };
            /** @description 막은 IP 에서 온 요청(network_blocked). 기간이 지나면 풀린다 */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CodedError"];
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
            /** @description 살아 있다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        status: "ok" | "unavailable";
                    };
                };
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
            /** @description 요청을 받을 수 있다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        status: "ok" | "unavailable";
                    };
                };
            };
            /** @description DB 에 닿지 않는다 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @enum {string} */
                        status: "ok" | "unavailable";
                    };
                };
            };
        };
    };
}
