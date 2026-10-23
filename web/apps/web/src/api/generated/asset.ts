// web/apps/web/src/api/generated/asset.ts
// docs/api/asset.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/asset/characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Characters
         * @description 자기 캐릭터의 목록. 최근에 고친 것부터다.
         */
        get: operations["list_characters_api_v1_asset_characters_get"];
        put?: never;
        /**
         * Create Character
         * @description 캐릭터를 만든다. 처음에는 비공개다. 1~2단계에는 운영자만 만든다(403 operator_only).
         */
        post: operations["create_character_api_v1_asset_characters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/characters/{character_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Character
         * @description 자기 캐릭터의 초안 하나.
         */
        get: operations["read_character_api_v1_asset_characters__character_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Character
         * @description 자기 캐릭터를 지운다. 판도 함께 지워진다.
         */
        delete: operations["delete_character_api_v1_asset_characters__character_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Character
         * @description 자기 캐릭터의 초안을 고친다. 보낸 칸만 바뀐다. 공개로 두는 것은 운영자만이다.
         */
        patch: operations["update_character_api_v1_asset_characters__character_id__patch"];
        trace?: never;
    };
    "/api/v1/asset/characters/{character_id}/publish-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Check Publish
         * @description 게시해 보기. 막히는 이유와 소개에서 걸러질 것을 본다. 판은 생기지 않는다.
         */
        get: operations["check_publish_api_v1_asset_characters__character_id__publish_check_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/characters/{character_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Versions
         * @description 자기 캐릭터의 판들. 최근 것부터다.
         */
        get: operations["list_versions_api_v1_asset_characters__character_id__versions_get"];
        put?: never;
        /**
         * Publish
         * @description 게시한다. 새 판과 소개에서 걸러 낸 것들을 돌려준다. 막는 것이 있으면 409 다.
         */
        post: operations["publish_api_v1_asset_characters__character_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/characters/{character_id}/versions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Version
         * @description 자기 캐릭터의 판 하나. 굳힌 문서까지다.
         */
        get: operations["read_version_api_v1_asset_characters__character_id__versions__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/images": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Image
         * @description 그림을 올린다. 본문은 그림 파일의 바이트다. 로그인을 먼저 보고, 그다음 본문을 읽는다.
         */
        post: operations["upload_image_api_v1_asset_images_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/images/{image_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Serve Image
         * @description 볼 수 있으면 nginx 에 넘길 머리말을 답한다. 그림의 바이트는 nginx 가 저장소에서 받아 내준다.
         */
        get: operations["serve_image_api_v1_asset_images__image_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/listings/characters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Public
         * @description 공개 캐릭터의 목록. 최근에 게시한 것부터다.
         */
        get: operations["list_public_api_v1_asset_listings_characters_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/listings/characters/{character_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Public
         * @description 공개 캐릭터 하나. 마지막 판의 문서다.
         */
        get: operations["read_public_api_v1_asset_listings_characters__character_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Me
         * @description 토큰이 유효하면 그 주인의 ID 를 돌려준다.
         */
        get: operations["read_me_api_v1_asset_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/personas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Personas
         * @description 자기 페르소나 전부. 기본이 먼저, 그다음 만든 차례다.
         */
        get: operations["list_personas_api_v1_asset_personas_get"];
        put?: never;
        /**
         * Create Persona
         * @description 페르소나를 만든다. 처음 만든 것이면 기본이다.
         */
        post: operations["create_persona_api_v1_asset_personas_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/personas/{persona_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Persona
         * @description 자기 페르소나 하나.
         */
        get: operations["read_persona_api_v1_asset_personas__persona_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Persona
         * @description 자기 페르소나를 지운다. 기본이었으면 가장 먼저 만든 것이 기본이 된다.
         */
        delete: operations["delete_persona_api_v1_asset_personas__persona_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Persona
         * @description 자기 페르소나를 고친다. 보낸 칸만 바뀐다. 내용이 바뀌면 revision 이 오른다.
         */
        patch: operations["update_persona_api_v1_asset_personas__persona_id__patch"];
        trace?: never;
    };
    "/api/v1/asset/personas/{persona_id}/default": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Make Default
         * @description 자기 페르소나 하나를 기본으로 둔다. 다른 것은 기본에서 내린다. 이미 기본이어도 200 이다.
         */
        put: operations["make_default_api_v1_asset_personas__persona_id__default_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/users/{public_id}/withdrawal": {
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
         * @description 탈퇴한 사람의 페르소나와 비공개 캐릭터, 쓰이지 않는 그림을 지운다.
         */
        post: operations["receive_withdrawal_api_v1_asset_service_users__public_id__withdrawal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/{caller}/characters/{character_id}/latest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Copy Latest
         * @description 토큰의 주인이 쓸 수 있는 캐릭터의 마지막 판.
         */
        get: operations["copy_latest_api_v1_asset_service__caller__characters__character_id__latest_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/{caller}/characters/{character_id}/latest/number": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Latest Number
         * @description 토큰의 주인이 쓸 수 있는 캐릭터의 마지막 판의 번호.
         */
        get: operations["read_latest_number_api_v1_asset_service__caller__characters__character_id__latest_number_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/{caller}/personas/{persona_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Copy Persona
         * @description 토큰의 주인의 페르소나 하나의 사본.
         */
        get: operations["copy_persona_api_v1_asset_service__caller__personas__persona_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/{caller}/personas/{persona_id}/revision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Revision
         * @description 토큰의 주인의 페르소나 하나의 지금 revision.
         */
        get: operations["read_revision_api_v1_asset_service__caller__personas__persona_id__revision_get"];
        put?: never;
        post?: never;
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
         * Affection
         * @description 캐릭터의 호감도. 값 하나(0~100)와 단계들이다. display 는 사람에게 보이는 방식이다
         *     (number: 숫자와 게이지, stage: 단계 이름과 게이지. 숫자는 chat 이 내려보내지 않는다).
         */
        Affection: {
            /** @default number */
            display: components["schemas"]["AffectionDisplay"];
            /**
             * Rules
             * @default []
             */
            rules: components["schemas"]["AffectionRule"][];
            /** Stages */
            stages: components["schemas"]["Stage"][];
            /**
             * Start
             * @default 0
             */
            start: number;
        };
        /**
         * AffectionDisplay
         * @description 호감도를 사람에게 보이는 방식. 숫자와 게이지, 또는 단계 이름과 게이지(숫자는 숨긴다).
         * @enum {string}
         */
        AffectionDisplay: "number" | "stage";
        /**
         * AffectionDocument
         * @description 캐릭터의 호감도.
         */
        AffectionDocument: {
            display: components["schemas"]["AffectionDisplay"];
            /** Rules */
            rules: components["schemas"]["AffectionRuleDocument"][];
            /** Stages */
            stages: components["schemas"]["StageDocument"][];
            /** Start */
            start: number;
        };
        /**
         * AffectionRule
         * @description 오르내리는 규칙 하나. on 의 행동을 하면 change 만큼 바꾼다(0~100 안으로 자른다).
         *     once 면 그 가지에서 처음 한 번만 바꾼다(처음 하는 일). id 는 캐릭터 안에서 고유하고, chat 이 "이미 했다"를 적는다.
         */
        AffectionRule: {
            /** Change */
            change: number;
            /** Id */
            id: string;
            on: components["schemas"]["Trigger"];
            /**
             * Once
             * @default false
             */
            once: boolean;
        };
        /**
         * AffectionRuleDocument
         * @description 오르내리는 규칙 하나. once 면 그 가지에서 처음 한 번만.
         */
        AffectionRuleDocument: {
            /** Change */
            change: number;
            /** Id */
            id: string;
            on: components["schemas"]["TriggerDocument"];
            /** Once */
            once: boolean;
        };
        /**
         * CharacterCopy
         * @description 다른 서버(chat, story)에 내주는 판. 대화를 시작할 때 가져가 고정한다.
         *
         *     마지막 판의 번호와 문서다. 가져간 쪽은 번호를 적어 두고,
         *     지금의 번호(CharacterVersionNumber)가 크면 "새 판이 있다"를 알린다.
         */
        CharacterCopy: {
            document: components["schemas"]["CharacterDocument"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            rating: components["schemas"]["Rating"];
            /** Version */
            version: number;
        };
        /**
         * CharacterCreate
         * @description 캐릭터를 만들 때 받는 값. 이름만 필수다. 처음에는 비공개다.
         */
        CharacterCreate: {
            affection?: components["schemas"]["Affection"] | null;
            /**
             * Age
             * @default
             */
            age: string;
            /**
             * Gender
             * @default
             */
            gender: string;
            /**
             * Greeting
             * @default
             */
            greeting: string;
            /** Image Id */
            image_id?: string | null;
            /**
             * Intro Html
             * @default
             */
            intro_html: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["Item"][];
            /** Name */
            name: string;
            /**
             * Paths
             * @default []
             */
            paths: components["schemas"]["Path"][];
            /**
             * Places
             * @default []
             */
            places: components["schemas"]["Place"][];
            /** @default all */
            rating: components["schemas"]["Rating"];
            /**
             * Speech Examples
             * @default
             */
            speech_examples: string;
            /**
             * Start Items
             * @default []
             */
            start_items: components["schemas"]["StartItem"][];
            /** Start Place */
            start_place?: string | null;
            /**
             * Starts
             * @default []
             */
            starts: components["schemas"]["Start"][];
            /**
             * Tags
             * @default []
             */
            tags: string[];
        };
        /**
         * CharacterDetail
         * @description 캐릭터의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null).
         */
        CharacterDetail: {
            affection: components["schemas"]["Affection"] | null;
            /** Age */
            age: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Gender */
            gender: string;
            /** Greeting */
            greeting: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
            /** Items */
            items: components["schemas"]["Item"][];
            /** Latest Version */
            latest_version: number | null;
            /** Name */
            name: string;
            /** Paths */
            paths: components["schemas"]["Path"][];
            /** Places */
            places: components["schemas"]["Place"][];
            /** Published At */
            published_at: string | null;
            rating: components["schemas"]["Rating"];
            /** Speech Examples */
            speech_examples: string;
            /** Start Items */
            start_items: components["schemas"]["StartItem"][];
            /** Start Place */
            start_place: string | null;
            /** Starts */
            starts: components["schemas"]["Start"][];
            /** Tags */
            tags: string[];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * CharacterDocument
         * @description 판에 굳힌 캐릭터. intro_html 은 허용 목록으로 거른 소개다.
         *     지도와 물건의 칸은 형식 2 에서 더했다. 형식 1 의 판을 읽을 수 있게 비어 있는 것이 기본이다.
         */
        CharacterDocument: {
            affection?: components["schemas"]["AffectionDocument"] | null;
            /** Age */
            age: string;
            /** Format */
            format: number;
            /** Gender */
            gender: string;
            /** Greeting */
            greeting: string;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemDocument"][];
            /** Name */
            name: string;
            /**
             * Paths
             * @default []
             */
            paths: components["schemas"]["PathDocument"][];
            /**
             * Places
             * @default []
             */
            places: components["schemas"]["PlaceDocument"][];
            rating: components["schemas"]["Rating"];
            /** Speech Examples */
            speech_examples: string;
            /**
             * Start Items
             * @default []
             */
            start_items: components["schemas"]["StartItemDocument"][];
            /** Start Place */
            start_place?: string | null;
            /** Starts */
            starts: components["schemas"]["StartDocument"][];
            /** Tags */
            tags: string[];
        };
        /**
         * CharacterPage
         * @description 목록의 한 쪽과 전체 개수.
         */
        CharacterPage: {
            /** Items */
            items: components["schemas"]["CharacterSummary"][];
            /** Total */
            total: number;
        };
        /**
         * CharacterSummary
         * @description 내 캐릭터 목록의 한 줄.
         */
        CharacterSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latest Version */
            latest_version: number | null;
            /** Name */
            name: string;
            rating: components["schemas"]["Rating"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * CharacterUpdate
         * @description 캐릭터를 고칠 때 받는 값. 보낸 칸만 바꾼다. 초안만 바뀐다. 게시한 판은 그대로다.
         *
         *     null 은 그림(image_id)만 받는다. 공개 범위(visibility)도 여기서 바꾼다(공개는 운영자만, 1~2단계).
         */
        CharacterUpdate: {
            affection?: components["schemas"]["Affection"] | null;
            /** Age */
            age?: string | null;
            /** Gender */
            gender?: string | null;
            /** Greeting */
            greeting?: string | null;
            /** Image Id */
            image_id?: string | null;
            /** Intro Html */
            intro_html?: string | null;
            /** Items */
            items?: components["schemas"]["Item"][] | null;
            /** Name */
            name?: string | null;
            /** Paths */
            paths?: components["schemas"]["Path"][] | null;
            /** Places */
            places?: components["schemas"]["Place"][] | null;
            rating?: components["schemas"]["Rating"] | null;
            /** Speech Examples */
            speech_examples?: string | null;
            /** Start Items */
            start_items?: components["schemas"]["StartItem"][] | null;
            /** Start Place */
            start_place?: string | null;
            /** Starts */
            starts?: components["schemas"]["Start"][] | null;
            /** Tags */
            tags?: string[] | null;
            visibility?: components["schemas"]["Visibility"] | null;
        };
        /**
         * CharacterVersionNumber
         * @description 캐릭터의 지금 판 번호. 화면을 열 때 한 번 묻는다. 문서는 싣지 않는다.
         */
        CharacterVersionNumber: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Version */
            version: number;
        };
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
         * ImageDetail
         * @description 올린 그림. url 은 그 그림을 내주는 주소다(소개 글의 img 에 그대로 쓴다).
         */
        ImageDetail: {
            /** Byte Size */
            byte_size: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            format: components["schemas"]["ImageFormat"];
            /** Height */
            height: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Url */
            url: string;
            /** Width */
            width: number;
        };
        /**
         * ImageFormat
         * @description 받는 형식. 값은 표(images.format)에 적는 이름이다.
         * @enum {string}
         */
        ImageFormat: "png" | "jpeg" | "webp";
        /**
         * Item
         * @description 물건 하나. 옷(clothing)은 건네면 상대의 차림에 들어간다. consumable 이면 쓰면 하나 없어진다.
         */
        Item: {
            /**
             * Consumable
             * @default false
             */
            consumable: boolean;
            /**
             * Description
             * @default
             */
            description: string;
            /** Id */
            id: string;
            /** Image Id */
            image_id?: string | null;
            /** @default thing */
            kind: components["schemas"]["ItemKind"];
            /** Name */
            name: string;
        };
        /**
         * ItemDocument
         * @description 물건 하나.
         */
        ItemDocument: {
            /**
             * Consumable
             * @default false
             */
            consumable: boolean;
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            kind: components["schemas"]["ItemKind"];
            /** Name */
            name: string;
        };
        /**
         * ItemKind
         * @description 물건의 종류. 옷은 건네면 상대의 차림에 들어간다(chat 의 장소와 소지품). 나머지는 그냥 물건이다.
         * @enum {string}
         */
        ItemKind: "thing" | "clothing";
        /**
         * MeResponse
         * @description 토큰의 주인.
         */
        MeResponse: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * Path
         * @description 두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이고 그만큼 시각이 흐른다.
         */
        Path: {
            /** A */
            a: string;
            /** B */
            b: string;
            /** Minutes */
            minutes: number;
        };
        /**
         * PathDocument
         * @description 두 장소(a, b) 사이의 길. 양쪽으로 다닌다. minutes 는 걸리는 시간(분)이다.
         */
        PathDocument: {
            /** A */
            a: string;
            /** B */
            b: string;
            /** Minutes */
            minutes: number;
        };
        /**
         * PersonaCopy
         * @description 다른 서버(chat, story, TRPG)에 내주는 페르소나의 사본. 세션을 시작하거나 바꿀 때 가져가 고정한다.
         *
         *     모델에 넣을 내용과 revision 만 싣는다. 기본인지와 시각은 그 서버가 쓰지 않는다.
         *     가져간 쪽은 revision 을 적어 두고, 지금의 revision(PersonaRevision)과 다르면 "새 설정으로 바꾸기"를 보인다.
         */
        PersonaCopy: {
            /** Age */
            age: string;
            /** Description */
            description: string;
            /** Form Of Address */
            form_of_address: string;
            /** Gender */
            gender: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string;
            /** Personality */
            personality: string;
            /** Revision */
            revision: number;
            /** Speech Examples */
            speech_examples: string;
        };
        /**
         * PersonaCreate
         * @description 페르소나를 만들 때 받는 값. 이름만 필수다.
         *
         *     기본인지는 받지 않는다. 처음 만든 것이 기본이 되고, 바꾸려면 기본으로 두는 주소를 부른다.
         */
        PersonaCreate: {
            /**
             * Age
             * @default
             */
            age: string;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Form Of Address
             * @default
             */
            form_of_address: string;
            /**
             * Gender
             * @default
             */
            gender: string;
            /** Image Id */
            image_id?: string | null;
            /** Name */
            name: string;
            /**
             * Personality
             * @default
             */
            personality: string;
            /**
             * Speech Examples
             * @default
             */
            speech_examples: string;
        };
        /**
         * PersonaDetail
         * @description 페르소나 하나. 주인만 본다.
         *
         *     revision 은 내용이 바뀔 때마다 오른다. 세션이 가져간 revision 과 다르면 "새 설정으로 바꾸기"를 보인다.
         */
        PersonaDetail: {
            /** Age */
            age: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** Form Of Address */
            form_of_address: string;
            /** Gender */
            gender: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Is Default */
            is_default: boolean;
            /** Name */
            name: string;
            /** Personality */
            personality: string;
            /** Revision */
            revision: number;
            /** Speech Examples */
            speech_examples: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * PersonaRevision
         * @description 페르소나의 지금 revision. 화면을 열 때 한 번 묻는다. 내용은 싣지 않는다.
         */
        PersonaRevision: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Revision */
            revision: number;
        };
        /**
         * PersonaUpdate
         * @description 페르소나를 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     보내지 않은 칸은 그대로다. 글의 칸을 비우려면 빈 글을 보낸다. null 은 그림(image_id)만 받는다(그림을 뗀다).
         */
        PersonaUpdate: {
            /** Age */
            age?: string | null;
            /** Description */
            description?: string | null;
            /** Form Of Address */
            form_of_address?: string | null;
            /** Gender */
            gender?: string | null;
            /** Image Id */
            image_id?: string | null;
            /** Name */
            name?: string | null;
            /** Personality */
            personality?: string | null;
            /** Speech Examples */
            speech_examples?: string | null;
        };
        /**
         * Place
         * @description 장소 하나(지도의 점). 그림(image_id)은 그 장소의 기본 배경이다. 설명은 모델이 읽는다.
         *     backgrounds 는 시간대마다의 배경이다. 그 시간대의 것이 없으면 기본 배경을 쓴다(chat 의 화면).
         */
        Place: {
            /**
             * Backgrounds
             * @default {}
             */
            backgrounds: {
                [key: string]: string;
            };
            /**
             * Description
             * @default
             */
            description: string;
            /** Id */
            id: string;
            /** Image Id */
            image_id?: string | null;
            /** Name */
            name: string;
        };
        /**
         * PlaceDocument
         * @description 장소 하나. 그림은 그 장소의 기본 배경이고, backgrounds 는 시간대마다의 배경이다.
         */
        PlaceDocument: {
            /**
             * Backgrounds
             * @default {}
             */
            backgrounds: {
                [key: string]: string;
            };
            /** Description */
            description: string;
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string;
        };
        /**
         * PublicCharacterDetail
         * @description 공개 캐릭터 하나. 마지막 판의 문서다.
         */
        PublicCharacterDetail: {
            document: components["schemas"]["CharacterDocument"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            /** Version */
            version: number;
        };
        /**
         * PublicCharacterPage
         * @description 공개 목록의 한 쪽과 전체 개수.
         */
        PublicCharacterPage: {
            /** Items */
            items: components["schemas"]["PublicCharacterSummary"][];
            /** Total */
            total: number;
        };
        /**
         * PublicCharacterSummary
         * @description 공개 목록의 한 줄. 마지막 판의 값이다.
         */
        PublicCharacterSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string;
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            rating: components["schemas"]["Rating"];
            /** Tags */
            tags: string[];
            /** Version */
            version: number;
        };
        /**
         * PublishCheck
         * @description 지금 게시하면 막히는 이유와 걸러질 것. 판을 만들지 않는다.
         *
         *     problems 는 게시가 409 로 돌려주는 것과 같은 이름이다. 비어 있으면 게시할 수 있다(ready).
         */
        PublishCheck: {
            /** Problems */
            problems: string[];
            /** Ready */
            ready: boolean;
            /** Removed */
            removed: components["schemas"]["RemovedItem"][];
        };
        /**
         * PublishResult
         * @description 게시한 결과. 새 판과, 소개에서 걸러 낸 것들(removed)이다.
         *
         *     걸러 낸 것이 있어도 게시는 된다. 거른 소개가 판에 들어간다. 화면이 removed 를 제작자에게 보인다.
         */
        PublishResult: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            document: components["schemas"]["CharacterDocument"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Note */
            note: string;
            /** Number */
            number: number;
            /** Removed */
            removed: components["schemas"]["RemovedItem"][];
        };
        /**
         * Rating
         * @description 이용 등급. 게임 서버와 같은 값이다.
         * @enum {string}
         */
        Rating: "all" | "adult";
        /**
         * RemovedItem
         * @description 게시할 때 소개에서 걸러 낸 것 하나(app/content/html.py).
         */
        RemovedItem: {
            kind: components["schemas"]["RemovedKind"];
            /** Name */
            name: string;
        };
        /**
         * RemovedKind
         * @description 걸러 낸 것의 종류.
         * @enum {string}
         */
        RemovedKind: "tag" | "attribute" | "style" | "link" | "image";
        /**
         * Stage
         * @description 호감도의 단계 하나. at 이상이면 이 단계다(다음 단계의 at 전까지).
         */
        Stage: {
            /** At */
            at: number;
            /** Name */
            name: string;
        };
        /**
         * StageDocument
         * @description 호감도의 단계 하나. at 이상이면 이 단계다.
         */
        StageDocument: {
            /** At */
            at: number;
            /** Name */
            name: string;
        };
        /**
         * Start
         * @description 시작 상황 하나. 대화를 열 때 사용자가 고른다. 제목은 목록에, 상황은 모델에 간다.
         *     hour 는 대화가 시작하는 시각(몇 시)이다. 1일째의 그 시각에서 시작해 이동과 시간 보내기로 흐른다(chat).
         */
        Start: {
            /**
             * Hour
             * @default 12
             */
            hour: number;
            /** Situation */
            situation: string;
            /** Title */
            title: string;
        };
        /**
         * StartDocument
         * @description 시작 상황 하나. hour 는 시작하는 시각(몇 시)이다.
         */
        StartDocument: {
            /**
             * Hour
             * @default 12
             */
            hour: number;
            /** Situation */
            situation: string;
            /** Title */
            title: string;
        };
        /**
         * StartItem
         * @description 사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수.
         */
        StartItem: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /** Item */
            item: string;
        };
        /**
         * StartItemDocument
         * @description 사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수.
         */
        StartItemDocument: {
            /** Count */
            count: number;
            /** Item */
            item: string;
        };
        /**
         * TimeOfDay
         * @description 하루의 어느 때. 장소의 시간대 배경을 고르는 열쇠다.
         *     경계는 TRPG 와 같다(trpg-server 의 app/calendar/clock.py, 2026-10-22 유저 결정). 계산은 chat 이 한다.
         * @enum {string}
         */
        TimeOfDay: "dawn" | "morning" | "day" | "evening" | "night";
        /**
         * Trigger
         * @description 호감도를 바꾸는 사용자의 행동. target 은 그 물건이나 장소의 id 다.
         */
        Trigger: {
            kind: components["schemas"]["TriggerKind"];
            /** Target */
            target: string;
        };
        /**
         * TriggerDocument
         * @description 호감도를 바꾸는 행동(종류, 대상).
         */
        TriggerDocument: {
            kind: components["schemas"]["TriggerKind"];
            /** Target */
            target: string;
        };
        /**
         * TriggerKind
         * @description 호감도를 바꾸는 사용자의 행동. TRPG 의 퀘스트 조건과 같은 (종류, 대상) 모양이다.
         *     물건을 건넸다(give_item), 장소에 갔다(reach_place), 물건을 썼다(use_item).
         * @enum {string}
         */
        TriggerKind: "give_item" | "reach_place" | "use_item";
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
         * VersionCreate
         * @description 게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다).
         */
        VersionCreate: {
            /**
             * Note
             * @default
             */
            note: string;
        };
        /**
         * VersionDetail
         * @description 판 하나. 굳힌 문서까지 싣는다.
         */
        VersionDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            document: components["schemas"]["CharacterDocument"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Note */
            note: string;
            /** Number */
            number: number;
        };
        /**
         * VersionSummary
         * @description 판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다.
         */
        VersionSummary: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Note */
            note: string;
            /** Number */
            number: number;
        };
        /**
         * Visibility
         * @description 누구에게 보이는가. 비공개는 만든 사람만, 공개는 게시한 판이 있으면 목록에 나온다.
         * @enum {string}
         */
        Visibility: "private" | "public";
        /**
         * WithdrawalResult
         * @description 답. 지운 것이 없어도(이미 지웠다, 이 서버에 그 사람의 것이 없다) 같다. 인증 서버는 이것을 보고 그만 보낸다.
         */
        WithdrawalResult: {
            /**
             * Status
             * @default processed
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
    list_characters_api_v1_asset_characters_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
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
                    "application/json": components["schemas"]["CharacterPage"];
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
    create_character_api_v1_asset_characters_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CharacterCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterDetail"];
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
    read_character_api_v1_asset_characters__character_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
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
                    "application/json": components["schemas"]["CharacterDetail"];
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
    delete_character_api_v1_asset_characters__character_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
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
    update_character_api_v1_asset_characters__character_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CharacterUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CharacterDetail"];
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
    check_publish_api_v1_asset_characters__character_id__publish_check_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
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
                    "application/json": components["schemas"]["PublishCheck"];
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
    list_versions_api_v1_asset_characters__character_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
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
                    "application/json": components["schemas"]["VersionSummary"][];
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
    publish_api_v1_asset_characters__character_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublishResult"];
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
    read_version_api_v1_asset_characters__character_id__versions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
                number: number;
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
                    "application/json": components["schemas"]["VersionDetail"];
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
    upload_image_api_v1_asset_images_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImageDetail"];
                };
            };
        };
    };
    serve_image_api_v1_asset_images__image_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                image_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 본문 없음. X-Accel-Redirect 와 X-Image-Source 로 nginx 가 그림을 내준다 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description 없거나 볼 수 없는 그림 */
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
    list_public_api_v1_asset_listings_characters_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
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
                    "application/json": components["schemas"]["PublicCharacterPage"];
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
    read_public_api_v1_asset_listings_characters__character_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
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
                    "application/json": components["schemas"]["PublicCharacterDetail"];
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
    read_me_api_v1_asset_me_get: {
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
    list_personas_api_v1_asset_personas_get: {
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
                    "application/json": components["schemas"]["PersonaDetail"][];
                };
            };
        };
    };
    create_persona_api_v1_asset_personas_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonaCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaDetail"];
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
    read_persona_api_v1_asset_personas__persona_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
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
                    "application/json": components["schemas"]["PersonaDetail"];
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
    delete_persona_api_v1_asset_personas__persona_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
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
    update_persona_api_v1_asset_personas__persona_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonaUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaDetail"];
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
    make_default_api_v1_asset_personas__persona_id__default_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
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
                    "application/json": components["schemas"]["PersonaDetail"];
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
    receive_withdrawal_api_v1_asset_service_users__public_id__withdrawal_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                public_id: string;
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
                    "application/json": components["schemas"]["WithdrawalResult"];
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
    copy_latest_api_v1_asset_service__caller__characters__character_id__latest_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
                caller: string;
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
                    "application/json": components["schemas"]["CharacterCopy"];
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
    read_latest_number_api_v1_asset_service__caller__characters__character_id__latest_number_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                character_id: string;
                caller: string;
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
                    "application/json": components["schemas"]["CharacterVersionNumber"];
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
    copy_persona_api_v1_asset_service__caller__personas__persona_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
                caller: string;
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
                    "application/json": components["schemas"]["PersonaCopy"];
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
    read_revision_api_v1_asset_service__caller__personas__persona_id__revision_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                persona_id: string;
                caller: string;
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
                    "application/json": components["schemas"]["PersonaRevision"];
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
