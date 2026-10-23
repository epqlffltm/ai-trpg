// web/apps/web/src/api/generated/chat.ts
// docs/api/chat.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/chat/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Conversations
         * @description 내 대화의 목록. 최근에 말한 것부터다. 가격 목록은 DB 를 읽기 전에 받는다(바깥을 기다리며 연결을 쥐지 않는다).
         */
        get: operations["list_conversations_api_v1_chat_conversations_get"];
        put?: never;
        /**
         * Start Conversation
         * @description 대화를 시작한다. 캐릭터의 마지막 판과 페르소나를 가져와 고정한다. 모델은 지난번 것이거나 고른 것이다.
         */
        post: operations["start_conversation_api_v1_chat_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Conversation
         * @description 대화 하나. 지금 보고 있는 가지의 말들까지. 가격 목록은 DB 를 읽기 전에 받는다.
         */
        get: operations["read_conversation_api_v1_chat_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Conversation
         * @description 대화를 지운다. 목록과 읽기에 더는 나오지 않는다.
         */
        delete: operations["delete_conversation_api_v1_chat_conversations__conversation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Act
         * @description 행동한다. 지도에서 이동(move), 물건 쓰기(use), 건네기(give, 한마디를 덧붙일 수 있다).
         *     서버가 할 수 있는지 보고 상태를 바꾼 뒤, 모델의 반응을 흘려보낸다. 반응을 받으니 한 번 청구한다.
         *     turn 의 user_message 가 행동 말(role action)이다(한마디를 덧붙였으면 그 한마디이고 action 이 행동 말이다).
         *     SSE 의 모양은 말 보내기와 같다.
         */
        post: operations["act_api_v1_chat_conversations__conversation_id__actions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/branch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Choose Branch
         * @description 다른 대안의 가지를 본다. 그 말 아래에서 가장 나중에 생긴 말이 끝이 된다. 바뀐 대화를 돌려준다.
         */
        put: operations["choose_branch_api_v1_chat_conversations__conversation_id__branch_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Send Message
         * @description 말을 보낸다. 사람의 말을 저장하고 모델의 답을 흘려보낸다. 끊겨도 서버는 끝까지 답을 저장한다.
         *     edit_of 가 있으면 그 사람의 말을 고친 새 가지다(원본은 남는다). 캐릭터의 말이면 422 not_editable.
         */
        post: operations["send_message_api_v1_chat_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/model": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Model
         * @description 대화의 모델을 바꾼다. 다음 말부터 그 모델로 쓰고 그 모델의 값으로 청구한다. 바꾼 모델을 돌려준다.
         */
        put: operations["change_model_api_v1_chat_conversations__conversation_id__model_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/notes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Notes
         * @description 대화의 기억 메모들.
         */
        get: operations["list_notes_api_v1_chat_conversations__conversation_id__notes_get"];
        put?: never;
        /**
         * Add Note
         * @description 기억 메모를 더한다. 다음 말부터 모델에 간다.
         */
        post: operations["add_note_api_v1_chat_conversations__conversation_id__notes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/notes/{note_id}": {
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
         * Delete Note
         * @description 기억 메모를 지운다.
         */
        delete: operations["delete_note_api_v1_chat_conversations__conversation_id__notes__note_id__delete"];
        options?: never;
        head?: never;
        /**
         * Edit Note
         * @description 기억 메모를 고친다.
         */
        patch: operations["edit_note_api_v1_chat_conversations__conversation_id__notes__note_id__patch"];
        trace?: never;
    };
    "/api/v1/chat/conversations/{conversation_id}/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Summary
         * @description 지금 가지의 굴리는 요약. 아직 없으면 null 이다.
         */
        get: operations["read_summary_api_v1_chat_conversations__conversation_id__summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/gallery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Unlocks
         * @description 내가 연 이벤트 씬들. 최근에 연 것부터다.
         */
        get: operations["list_unlocks_api_v1_chat_gallery_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/generations/{generation_id}/stop": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Stop Generation
         * @description 모델을 부르는 것을 멈춘다(공급자의 호출도 끊는다).
         *     받은 만큼 partial 로 저장하고 청구한다. 받은 글이 없으면 반환한다.
         *
         *     멈출 생성이 없으면(끝났다, 남의 것이다, 이 서버에서 도는 것이 아니다) 404 generation_not_running 이다.
         */
        post: operations["stop_generation_api_v1_chat_generations__generation_id__stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/me": {
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
        get: operations["read_me_api_v1_chat_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/messages/{message_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Edit Message
         * @description 캐릭터의 말을 그 자리에서 고친다(상대의 말 고치기). 고친 표시(edited)가 붙고 선택지는 지워진다. 청구하지 않는다.
         *     사람의 말은 422 not_editable(말 보내기의 edit_of 로 새 가지를 만든다). 답을 쓰는 중이면 409.
         */
        patch: operations["edit_message_api_v1_chat_messages__message_id__patch"];
        trace?: never;
    };
    "/api/v1/chat/messages/{message_id}/continue": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Continue Message
         * @description 끊긴 답(partial)에 이어 쓴다. 지금 가지의 끝인 말만 된다.
         *
         *     새 호출이라 새로 청구한다. SSE 의 turn 에 continues(그 말의 id)가 실리고, delta 는 그 말 끝에 붙일 글이다.
         *     done 의 말은 이어 붙인 그 말 전체다. 다 쓰면 complete, 또 끊기면 partial 이라 다시 이어 쓸 수 있다.
         */
        post: operations["continue_message_api_v1_chat_messages__message_id__continue_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/messages/{message_id}/regenerate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Regenerate
         * @description 그 말에 다시 답한다.
         *     캐릭터의 답이면 같은 사람의 말에 새 대안을, 사람의 말이면(답을 못 받았다) 그 말에 답을 쓴다.
         *
         *     새 호출이라 새로 청구한다. 앞의 답은 남고, 대화의 가지는 새 답으로 옮겨 간다. SSE 의 모양은 말 보내기와 같다.
         */
        post: operations["regenerate_api_v1_chat_messages__message_id__regenerate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Models
         * @description 대화에 고를 수 있는 모델들과 그 값. 회사, 이름표 순서다.
         */
        get: operations["list_models_api_v1_chat_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/chat/service/users/{public_id}/withdrawal": {
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
         * @description 탈퇴한 사람의 대화와 캐릭터의 사본을 지운다. 청구 기록은 대화와 끊어 남긴다.
         */
        post: operations["receive_withdrawal_api_v1_chat_service_users__public_id__withdrawal_post"];
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
         * AffectionDocument
         * @description 캐릭터의 호감도. display 는 number(숫자와 게이지)나 stage(단계 이름과 게이지, 숫자를 내려보내지 않는다)다.
         */
        AffectionDocument: {
            /** Display */
            display: string;
            /**
             * Rules
             * @default []
             */
            rules: components["schemas"]["AffectionRuleDocument"][];
            /** Stages */
            stages: components["schemas"]["StageDocument"][];
            /** Start */
            start: number;
        };
        /**
         * AffectionOut
         * @description 사용자에 대한 상대의 호감도. 보이는 방식(display)은 제작자가 정한다.
         *     number 면 value(0~100)가 실리고, stage 면 value 는 null 이다(숫자를 내려보내지 않는다. 화면의 코드로 숨기지 않는다).
         *     stage 는 지금 단계의 이름, stage_index 는 그 자리(0 부터), stages 는 단계의 수다(게이지를 그린다).
         */
        AffectionOut: {
            /** Display */
            display: string;
            /** Stage */
            stage: string;
            /** Stage Index */
            stage_index: number;
            /** Stages */
            stages: number;
            /** Value */
            value: number | null;
        };
        /**
         * AffectionRuleDocument
         * @description 오르내리는 규칙 하나. on 의 행동을 하면 change 만큼. once 면 그 가지에서 처음 한 번만.
         */
        AffectionRuleDocument: {
            /** Change */
            change: number;
            /** Id */
            id: string;
            on: components["schemas"]["TriggerDocument"];
            /**
             * Once
             * @default false
             */
            once: boolean;
        };
        /**
         * BranchChoice
         * @description 볼 가지. 대안 가운데 하나의 id 다. 그 말 아래에서 가장 나중에 생긴 말이 가지의 끝이 된다.
         */
        BranchChoice: {
            /**
             * Message Id
             * Format: uuid
             */
            message_id: string;
        };
        /**
         * CharacterDocument
         * @description 판에 굳힌 캐릭터. intro_html 은 asset 서버가 허용 목록으로 거른 소개다.
         */
        CharacterDocument: {
            affection?: components["schemas"]["AffectionDocument"] | null;
            /** Age */
            age: string;
            /**
             * Event Scenes
             * @default []
             */
            event_scenes: components["schemas"]["EventSceneDocument"][];
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
             * Sprites
             * @default []
             */
            sprites: components["schemas"]["SpriteDocument"][];
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
         * CharacterOut
         * @description 대화 하나에 싣는 캐릭터. 가져온 판의 문서까지다.
         */
        CharacterOut: {
            document: components["schemas"]["CharacterDocument"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            rating: components["schemas"]["Rating"];
            /** Version */
            version: number;
        };
        /**
         * CharacterSummary
         * @description 목록에 싣는 캐릭터. id 는 asset 서버의 캐릭터 id 다.
         */
        CharacterSummary: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string;
            rating: components["schemas"]["Rating"];
            /** Version */
            version: number;
        };
        /**
         * ClockOut
         * @description 대화 안의 지금 시각. day 는 1 부터(며칠째), hour 는 0~23, minute 는 0~59, time_of_day 는 시간대다.
         */
        ClockOut: {
            /** Day */
            day: number;
            /** Hour */
            hour: number;
            /** Minute */
            minute: number;
            time_of_day: components["schemas"]["TimeOfDay"];
        };
        /**
         * ConversationCreate
         * @description 대화를 시작할 때 받는 값. 캐릭터와 시작 상황만 고르고 들어간다(2026-10-20). 페르소나와 모델은 지난번 것을 쓴다.
         *
         *     persona_id 는 셋 중 하나다.
         *       - 보내지 않으면: 지난번 대화의 페르소나를 쓴다. 지난번에 없었거나 그 페르소나가 지워졌으면 페르소나 없이 시작한다
         *       - null 을 보내면: 페르소나 없이 시작한다
         *       - id 를 보내면: 그 페르소나다. 없거나 남의 것이면 404 다
         *
         *     model 도 셋 중 하나다.
         *       - 보내지 않으면: 지난번 대화의 모델을 쓴다. 지난번에 없었거나 이 대화에 고를 수 없으면 모델 없이 시작한다
         *       - null 을 보내면: 모델 없이 시작한다. 말을 보내기 전에 고른다
         *       - 이름표를 보내면: 그 모델이다. 이 대화에 고를 수 없으면 422 model_unavailable 이다
         */
        ConversationCreate: {
            /**
             * Character Id
             * Format: uuid
             */
            character_id: string;
            /** Model */
            model?: string | null;
            /** Persona Id */
            persona_id?: string | null;
            /**
             * Start
             * @default 0
             */
            start: number;
        };
        /**
         * ConversationDetail
         * @description 대화 하나. messages 는 지금 보고 있는 가지의 말들이다. 첫 말부터 차례로. 말마다 그 대안들의 id 가 실린다.
         *
         *     generating 이 참이면 답을 쓰는 중이다. 화면이 보내기를 막고, 끝난 뒤 다시 읽는다.
         */
        ConversationDetail: {
            character: components["schemas"]["CharacterOut"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Generating */
            generating: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Messages */
            messages: components["schemas"]["PathMessageOut"][];
            model: components["schemas"]["ConversationModelOut"] | null;
            persona: components["schemas"]["PersonaOut"] | null;
            start: components["schemas"]["StartOut"];
            state: components["schemas"]["StateOut"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * ConversationModelOut
         * @description 대화에 싣는 모델. usable 이 거짓이면 이 대화에 더는 고를 수 없는 모델이다
         *     (꺼졌다, 은퇴했다, 성인 등급의 대화에 쓸 수 없게 됐다).
         *
         *     화면이 "모델을 다시 골라 주세요"를 보인다. 서버는 몰래 다른 모델로 바꾸지 않는다.
         */
        ConversationModelOut: {
            /** Display Name */
            display_name: string;
            grade: components["schemas"]["Grade"];
            /** Retires On */
            retires_on: string | null;
            /** Slug */
            slug: string;
            /** Usable */
            usable: boolean;
            /** Vendor */
            vendor: string;
        };
        /**
         * ConversationPage
         * @description 목록의 한 쪽과 전체 개수. 게임 서버의 GET /tables 와 같은 모양이다(#593).
         */
        ConversationPage: {
            /** Items */
            items: components["schemas"]["ConversationSummary"][];
            /** Total */
            total: number;
        };
        /**
         * ConversationSummary
         * @description 목록의 한 줄.
         */
        ConversationSummary: {
            character: components["schemas"]["CharacterSummary"];
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
            model: components["schemas"]["ConversationModelOut"] | null;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * EventSceneDocument
         * @description 이벤트 씬 하나. collectible 이면 해금 대상이다. description 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다.
         */
        EventSceneDocument: {
            /**
             * Collectible
             * @default true
             */
            collectible: boolean;
            /**
             * Description
             * @default
             */
            description: string;
            /** Id */
            id: string;
            /**
             * Image Id
             * Format: uuid
             */
            image_id: string;
            /** Title */
            title: string;
            when: components["schemas"]["SceneConditionDocument"];
        };
        /**
         * GiveAction
         * @description 소지품의 물건을 상대에게 건넨다. 하나 줄고, 옷이면 상대가 입는다.
         *     words 는 덧붙이는 한마디다(없으면 행동만). 행동과 말을 한 턴에 붙이고 반응을 한 번 받는다.
         */
        GiveAction: {
            /** Item */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "give";
            /** Words */
            words?: string | null;
        };
        /**
         * Grade
         * @description 보이는 분류. 목록을 묶어 보이는 데만 쓴다. 값은 모델마다 모델 목록의 파일에 적는다.
         * @enum {string}
         */
        Grade: "basic" | "standard" | "premium";
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
         * HoldingOut
         * @description 가진 물건 하나와 그 수.
         */
        HoldingOut: {
            /** Count */
            count: number;
            /** Item */
            item: string;
        };
        /**
         * ItemDocument
         * @description 물건 하나. kind 는 thing 이나 clothing(건네면 상대의 차림에 들어간다)이다. 모르는 종류도 받아 둔다.
         *     consumable 이면 쓰면 하나 없어진다.
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
            /** Kind */
            kind: string;
            /** Name */
            name: string;
        };
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
         * MessageCreate
         * @description 보내는 말.
         */
        MessageCreate: {
            /** Content */
            content: string;
            /** Edit Of */
            edit_of?: string | null;
        };
        /**
         * MessageEdit
         * @description 캐릭터의 말을 고친 글.
         */
        MessageEdit: {
            /** Content */
            content: string;
        };
        /**
         * MessageOut
         * @description 말 하나.
         */
        MessageOut: {
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Edited
             * @default false
             */
            edited: boolean;
            /** Event Scene */
            event_scene?: string | null;
            /** Expression */
            expression?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Role */
            role: string;
            /** Status */
            status: string;
            /**
             * Suggestions
             * @default []
             */
            suggestions: string[];
        };
        /**
         * ModelChoice
         * @description 대화의 모델을 바꿀 때 받는 값.
         */
        ModelChoice: {
            /** Model */
            model: string;
        };
        /**
         * ModelList
         * @description 고를 수 있는 모델들. 회사, 이름표 순서다. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다.
         */
        ModelList: {
            /** Free */
            free: boolean;
            /** Items */
            items: components["schemas"]["ModelOut"][];
        };
        /**
         * ModelOut
         * @description 고를 수 있는 모델 하나와 말 한 번의 값.
         *
         *     credits 는 결제 서버가 정한 값(글자, "30")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
         *     tier 가 premium 이면 골드(유료 크레딧)로만 낸다. grade 는 화면의 묶음(basic, standard, premium)이다.
         */
        ModelOut: {
            /** Allows Adult */
            allows_adult: boolean;
            /** Credits */
            credits: string | null;
            /** Display Name */
            display_name: string;
            grade: components["schemas"]["Grade"];
            next: components["schemas"]["NextPriceOut"] | null;
            /** Promo */
            promo: boolean;
            /** Retires On */
            retires_on: string | null;
            /** Slug */
            slug: string;
            tier: components["schemas"]["Tier"] | null;
            /** Vendor */
            vendor: string;
        };
        /**
         * MoveAction
         * @description 지도에서 장소를 골라 간다. 지금 있는 곳과 길로 바로 이어진 곳만 된다.
         */
        MoveAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move";
            /** Place */
            place: string;
        };
        /**
         * NextPriceOut
         * @description 예약된 값의 바뀜. credits 가 null 이면 effective_at 부터 팔지 않는다.
         */
        NextPriceOut: {
            /** Credits */
            credits: string | null;
            /**
             * Effective At
             * Format: date-time
             */
            effective_at: string;
            /** Promo */
            promo: boolean;
            tier: components["schemas"]["Tier"] | null;
        };
        /**
         * NoteOut
         * @description 메모 하나. source 는 누가 썼는가(user, summary)다.
         */
        NoteOut: {
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
            source: components["schemas"]["NoteSource"];
            /** Text */
            text: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * NoteSource
         * @description 메모를 누가 썼는가.
         * @enum {string}
         */
        NoteSource: "user" | "summary";
        /**
         * NoteWrite
         * @description 메모를 쓰거나 고칠 때 받는 글.
         */
        NoteWrite: {
            /** Text */
            text: string;
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
         * PathMessageOut
         * @description 지금 가지의 말 하나와 그 대안들. alternatives 는 같은 부모 아래의 말들의 id 다(먼저 생긴 것부터, 이 말도 든다).
         *
         *     화면이 "< 2/3 >" 를 그리고, 다른 대안을 고르면 PUT /conversations/{id}/branch 로 그 가지를 본다.
         */
        PathMessageOut: {
            /** Alternatives */
            alternatives: string[];
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Edited
             * @default false
             */
            edited: boolean;
            /** Event Scene */
            event_scene?: string | null;
            /** Expression */
            expression?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Role */
            role: string;
            /** Status */
            status: string;
            /**
             * Suggestions
             * @default []
             */
            suggestions: string[];
        };
        /**
         * PersonaOut
         * @description 대화에 가져온 페르소나의 사본. id 는 asset 서버의 페르소나 id 다.
         */
        PersonaOut: {
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
         * PlaceDocument
         * @description 장소 하나. id 는 캐릭터 안에서 고유하다. 그림(image_id)은 그 장소의 기본 배경이다.
         *     backgrounds 는 시간대(dawn, morning, day, evening, night)마다의 배경이다.
         *     모르는 시간대도 받아 둔다(쓰이지 않을 뿐이다).
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
         * Rating
         * @description 이용 등급. asset 서버, 게임 서버와 같은 값이다.
         * @enum {string}
         */
        Rating: "all" | "adult";
        /**
         * SceneConditionDocument
         * @description 이벤트 씬이 나오는 조건. kind 는 reach_place(장소의 id), give_item(물건의 id), affection_stage(단계의 이름)다.
         *     모르는 종류도 받아 둔다(맞는 일이 없을 뿐이다).
         */
        SceneConditionDocument: {
            /** Kind */
            kind: string;
            /** Target */
            target: string;
        };
        /**
         * SpriteDocument
         * @description 캐릭터 그림 하나(배경이 투명한 서 있는 그림). expression 은 표정(빈 글이면 기본),
         *     outfit 은 이 그림의 차림인 옷(물건의 id, 없으면 처음 차림)이다.
         */
        SpriteDocument: {
            /**
             * Expression
             * @default
             */
            expression: string;
            /** Id */
            id: string;
            /**
             * Image Id
             * Format: uuid
             */
            image_id: string;
            /** Outfit */
            outfit?: string | null;
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
         * StartDocument
         * @description 시작 상황 하나. 제목은 목록에, 상황은 모델에 간다. hour 는 시작하는 시각(몇 시, 0~23)이다.
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
         * StartOut
         * @description 고른 시작 상황. hour 는 대화가 시작한 시각(1일째 몇 시)이다.
         */
        StartOut: {
            /** Hour */
            hour: number;
            /** Situation */
            situation: string;
            /** Title */
            title: string;
        };
        /**
         * StateOut
         * @description 지금 보고 있는 가지의 끝의 상태. place 는 지금 있는 장소(지도가 없으면 null),
         *     minutes 는 대화를 시작한 뒤 흐른 시간(분), visited 는 가 본 장소들이다(화면이 안개를 그린다).
         *     outfit 은 상대가 입은 옷들이다.
         */
        StateOut: {
            affection: components["schemas"]["AffectionOut"] | null;
            /** Background */
            background: string | null;
            clock: components["schemas"]["ClockOut"];
            /** Inventory */
            inventory: components["schemas"]["HoldingOut"][];
            /** Minutes */
            minutes: number;
            /** Outfit */
            outfit: string[];
            /** Place */
            place: string | null;
            /** Sprite */
            sprite: string | null;
            /** Visited */
            visited: string[];
        };
        /**
         * SummaryOut
         * @description 지금 가지의 요약(읽기만). covered_up_to 는 요약한 마지막 말의 id 다(첫 말부터 그 말까지를 요약했다).
         */
        SummaryOut: {
            /**
             * Covered Up To
             * Format: uuid
             */
            covered_up_to: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Text */
            text: string;
        };
        /**
         * Tier
         * @description 결제 서버 가격표의 등급. 결제에 쓰는 등급은 이것이 기준이다(model-pricing-plan 9-1).
         *
         *     결제 서버가 모르는 등급을 보내면 목록 전체를 읽지 못한다(503).
         *     그래서 결제 서버는 게임 서버와 chat 서버가 등급을 안 뒤에 그 줄을 넣는다.
         * @enum {string}
         */
        Tier: "basic" | "standard" | "premium";
        /**
         * TimeOfDay
         * @description 하루의 어느 때. 배경을 고르고, 모델이 밝기와 분위기를 맞춘다. asset 서버의 TimeOfDay 와 같은 이름이다.
         * @enum {string}
         */
        TimeOfDay: "dawn" | "morning" | "day" | "evening" | "night";
        /**
         * TriggerDocument
         * @description 호감도를 바꾸는 행동. kind 는 give_item, reach_place, use_item 이다.
         *     모르는 종류도 받아 둔다(맞는 행동이 없을 뿐이다).
         */
        TriggerDocument: {
            /** Kind */
            kind: string;
            /** Target */
            target: string;
        };
        /**
         * UnlockOut
         * @description 연 이벤트 씬 하나. character_id 는 asset 서버의 캐릭터 id 다.
         */
        UnlockOut: {
            /**
             * Character Id
             * Format: uuid
             */
            character_id: string;
            /** Scene Id */
            scene_id: string;
            /**
             * Unlocked At
             * Format: date-time
             */
            unlocked_at: string;
        };
        /**
         * UnlockPage
         * @description 목록의 한 쪽과 전체 개수. 대화 목록과 같은 모양이다.
         */
        UnlockPage: {
            /** Items */
            items: components["schemas"]["UnlockOut"][];
            /** Total */
            total: number;
        };
        /**
         * UseAction
         * @description 소지품의 물건을 쓴다. 쓰면 없어지는 물건이면 하나 준다.
         */
        UseAction: {
            /** Item */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "use";
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
         * WaitAction
         * @description 시간을 보낸다. 다음 시간대가 시작하는 시각까지 흐른다(밤이면 다음 날 새벽). 지도가 없어도 된다.
         */
        WaitAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "wait";
        };
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
    list_conversations_api_v1_chat_conversations_get: {
        parameters: {
            query?: {
                /** @description asset 서버의 캐릭터 id. 주면 그 캐릭터의 대화만 */
                character_id?: string | null;
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
                    "application/json": components["schemas"]["ConversationPage"];
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
    start_conversation_api_v1_chat_conversations_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetail"];
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
    read_conversation_api_v1_chat_conversations__conversation_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
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
                    "application/json": components["schemas"]["ConversationDetail"];
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
    delete_conversation_api_v1_chat_conversations__conversation_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
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
    act_api_v1_chat_conversations__conversation_id__actions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MoveAction"] | components["schemas"]["UseAction"] | components["schemas"]["GiveAction"] | components["schemas"]["WaitAction"];
            };
        };
        responses: {
            /** @description SSE. app/turns/schemas.py 의 메시지들 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    choose_branch_api_v1_chat_conversations__conversation_id__branch_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BranchChoice"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationDetail"];
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
    send_message_api_v1_chat_conversations__conversation_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description SSE. app/turns/schemas.py 의 메시지들 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    change_model_api_v1_chat_conversations__conversation_id__model_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelChoice"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationModelOut"];
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
    list_notes_api_v1_chat_conversations__conversation_id__notes_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
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
                    "application/json": components["schemas"]["NoteOut"][];
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
    add_note_api_v1_chat_conversations__conversation_id__notes_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteOut"];
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
    delete_note_api_v1_chat_conversations__conversation_id__notes__note_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
                note_id: string;
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
    edit_note_api_v1_chat_conversations__conversation_id__notes__note_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
                note_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NoteWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteOut"];
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
    read_summary_api_v1_chat_conversations__conversation_id__summary_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
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
                    "application/json": components["schemas"]["SummaryOut"] | null;
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
    list_unlocks_api_v1_chat_gallery_get: {
        parameters: {
            query?: {
                /** @description asset 서버의 캐릭터 id. 주면 그 캐릭터의 것만 */
                character_id?: string | null;
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
                    "application/json": components["schemas"]["UnlockPage"];
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
    stop_generation_api_v1_chat_generations__generation_id__stop_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                generation_id: string;
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
    read_me_api_v1_chat_me_get: {
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
    edit_message_api_v1_chat_messages__message_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageEdit"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageOut"];
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
    continue_message_api_v1_chat_messages__message_id__continue_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description SSE. app/turns/schemas.py 의 메시지들 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    regenerate_api_v1_chat_messages__message_id__regenerate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description SSE. app/turns/schemas.py 의 메시지들 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    list_models_api_v1_chat_models_get: {
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
                    "application/json": components["schemas"]["ModelList"];
                };
            };
        };
    };
    receive_withdrawal_api_v1_chat_service_users__public_id__withdrawal_post: {
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
