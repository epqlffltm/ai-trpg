// web/apps/web/src/api/generated/story.ts
// docs/api/story.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/story/admin/message-reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Reports
         * @description 열린 신고의 목록. minor 가 먼저, 그다음 오래된 것부터. 세션의 글은 싣지 않는다.
         */
        get: operations["list_reports_api_v1_story_admin_message_reports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/admin/message-reports/{report_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Report
         * @description 신고 하나와 굳힌 세션의 글. 볼 때마다 감사 기록에 남는다(사유가 필수다). 없으면 404 다.
         */
        get: operations["read_report_api_v1_story_admin_message_reports__report_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/admin/message-reports/{report_id}/outcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Handle Report
         * @description 신고를 처리한다. 없으면 404, 이미 처리했으면 409 다.
         */
        put: operations["handle_report_api_v1_story_admin_message_reports__report_id__outcome_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Conversations
         * @description 내 세션의 목록. 최근의 것부터다. 가격 목록은 DB 를 읽기 전에 받는다(바깥을 기다리며 연결을 쥐지 않는다).
         */
        get: operations["list_conversations_api_v1_story_conversations_get"];
        put?: never;
        /**
         * Start Conversation
         * @description 세션을 시작한다. 세계관의 마지막 판을 가져와 고정한다. 페르소나와 모델은 지난번 것이거나 고른 것이다.
         */
        post: operations["start_conversation_api_v1_story_conversations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Conversation
         * @description 세션 하나. 가져온 판과 지금 가지의 말까지. 가격 목록은 DB 를 읽기 전에 받는다.
         */
        get: operations["read_conversation_api_v1_story_conversations__conversation_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Conversation
         * @description 세션을 지운다. 목록과 읽기에 더는 나오지 않는다. 없거나 남의 것이면 404 conversation_not_found 다.
         */
        delete: operations["delete_conversation_api_v1_story_conversations__conversation_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/actions": {
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
         * @description 행동한다. 이동(move), 시간 보내기(pass_time), 하루 마치기(end_day), 선택지 고르기(choose), 고백(confess),
         *     건네기(give).
         *     엔진이 할 수 있는지 보고 상태를 바꾼 뒤(이벤트가 열리고 엔딩을 볼 수 있다), 모델의 반응을 흘려보낸다.
         *     반응을 받으니 한 번 청구한다. turn 의 user_message 가 행동 말(role action)이고 state 가 그 뒤의 상태다.
         *     SSE 의 모양은 말 보내기와 같다.
         */
        post: operations["act_api_v1_story_conversations__conversation_id__actions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/branch": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Choose Branch
         * @description 다른 대안의 가지를 본다. 그 말 아래에서 가장 나중에 생긴 말이 끝이 된다. 바뀐 세션(그 가지의 말과 상태)을 돌려준다.
         *     그 세션의 말이 아니면 404 message_not_found, 답을 쓰는 중이면 409 generation_in_progress 다.
         */
        put: operations["choose_branch_api_v1_story_conversations__conversation_id__branch_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/messages": {
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
         * @description 말을 보낸다. 사람의 말을 저장하고, 장면의 인물들과 서술의 답을 말 조각으로 흘려보낸다.
         *     끊겨도 서버는 끝까지 답을 저장한다. 말은 상태(시각, 장소, 호감도)를 바꾸지 않는다.
         *     edit_of 가 있으면 그 사람의 말을 고친 새 가지다(원본은 남는다). 사람의 말이 아니면 422 not_editable,
         *     그 세션의 말이 아니면 404 message_not_found 다.
         */
        post: operations["send_message_api_v1_story_conversations__conversation_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/model": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Model
         * @description 세션의 모델을 바꾼다. 다음 말부터 그 모델로 쓰고 그 모델의 값으로 청구한다. 바꾼 모델을 돌려준다.
         */
        put: operations["change_model_api_v1_story_conversations__conversation_id__model_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/notes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Notes
         * @description 세션의 기억 메모들.
         */
        get: operations["list_notes_api_v1_story_conversations__conversation_id__notes_get"];
        put?: never;
        /**
         * Add Note
         * @description 기억 메모를 더한다. 다음 말부터 모델에 간다.
         */
        post: operations["add_note_api_v1_story_conversations__conversation_id__notes_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/notes/{note_id}": {
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
        delete: operations["delete_note_api_v1_story_conversations__conversation_id__notes__note_id__delete"];
        options?: never;
        head?: never;
        /**
         * Edit Note
         * @description 기억 메모를 고친다.
         */
        patch: operations["edit_note_api_v1_story_conversations__conversation_id__notes__note_id__patch"];
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/notes/{note_id}/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Accept Note
         * @description 요약이 제안한 메모를 받아들인다. 다음 말부터 모델에 간다. 버리려면 지운다.
         */
        post: operations["accept_note_api_v1_story_conversations__conversation_id__notes__note_id__accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/persona": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Persona
         * @description 세션의 페르소나를 바꾼다. 다음 말부터 그 페르소나로 쓴다. 같은 id 면 asset 서버의 새 설정으로 바꾼다.
         *     고른 페르소나가 없으면 404 persona_not_found 이고 그대로 둔다. 바꾼 페르소나를 돌려준다.
         */
        put: operations["change_persona_api_v1_story_conversations__conversation_id__persona_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/summary": {
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
        get: operations["read_summary_api_v1_story_conversations__conversation_id__summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/conversations/{conversation_id}/transcript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Transcript
         * @description 내 세션의 기록. 지금 보고 있는 가지의 말들이다. 없거나 볼 수 없는 세션이면 404.
         */
        get: operations["download_transcript_api_v1_story_conversations__conversation_id__transcript_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/endings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Endings
         * @description 그 세계관에서 내가 본 엔딩들.
         */
        get: operations["list_endings_api_v1_story_endings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/gallery": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Illustrations
         * @description 그 세계관에서 내가 연 일러스트들.
         */
        get: operations["list_illustrations_api_v1_story_gallery_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/generations/{generation_id}/stop": {
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
         *     받은 만큼 partial 로 저장하고 청구한다. 받은 조각이 없으면 반환한다.
         *
         *     멈출 생성이 없으면(끝났다, 남의 것이다, 이 서버에서 도는 것이 아니다) 404 generation_not_running 이다.
         */
        post: operations["stop_generation_api_v1_story_generations__generation_id__stop_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/me": {
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
        get: operations["read_me_api_v1_story_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/messages/{message_id}": {
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
         * @description 답을 그 자리에서 고친다. 조각마다 고친 글을 차례대로 보낸다. 말하는 사람은 그대로이고 고친 표시(edited)가 붙는다.
         *     청구하지 않는다. 답이 아니면 422 not_editable, 조각의 수가 다르면 422 segments_mismatch,
         *     말이 없거나 남의 것이면 404 message_not_found, 답을 쓰는 중이면 409 generation_in_progress 다.
         */
        patch: operations["edit_message_api_v1_story_messages__message_id__patch"];
        trace?: never;
    };
    "/api/v1/story/messages/{message_id}/continue": {
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
         * @description 끊긴 답(partial)에 이어 쓴다. 지금 가지의 끝인 답만 된다. 엔진은 다시 판정하지 않는다.
         *
         *     새 호출이라 새로 청구한다. SSE 의 turn 에 continues(그 답의 id)가 실린다.
         *     첫 segment 앞의 delta 는 그 답의 마지막 조각에 붙는 글이고, segment 가 오면 새 조각이다.
         *     done 의 말은 이어 붙인 그 답 전체다. 다 쓰면 complete, 또 끊기면 partial 이라 다시 이어 쓸 수 있다.
         */
        post: operations["continue_message_api_v1_story_messages__message_id__continue_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/messages/{message_id}/regenerate": {
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
         * @description 그 말에 다시 답한다. 답이면 같은 말(사람의 말이나 행동 말)에 새 대안을, 사람의 말이나 행동 말이면(답을 못 받았다)
         *     그 말에 답을 쓴다. 엔진은 다시 판정하지 않는다. 그 말의 상태와, 그 말에 적힌 이벤트와 엔딩의 장면으로 쓴다.
         *
         *     새 호출이라 새로 청구한다. 앞의 답은 남고, 세션의 가지는 새 답으로 옮겨 간다. SSE 의 모양은 말 보내기와 같다.
         */
        post: operations["regenerate_api_v1_story_messages__message_id__regenerate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/messages/{message_id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Report Message
         * @description 모델의 답을 신고한다. 그 답과 앞의 말 몇 개를 신고에 굳혀 둔다(운영자는 이것만 본다).
         *     없거나 남의 세션의 말이면 404, 사람의 말이나 행동 말이면 422, 이미 신고했으면 409 다.
         */
        post: operations["report_message_api_v1_story_messages__message_id__reports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Models
         * @description 세션에 고를 수 있는 모델들과 그 값. 회사, 이름표 순서다.
         */
        get: operations["list_models_api_v1_story_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/story/service/users/{public_id}/withdrawal": {
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
         * @description 탈퇴한 사람의 세션과 판의 사본, 계정의 기록을 지운다. 청구 기록은 세션과 끊어 남긴다.
         */
        post: operations["receive_withdrawal_api_v1_story_service_users__public_id__withdrawal_post"];
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
         * CastAffectionOut
         * @description 인물 창의 호감도. display 는 보이는 법(숫자, 단계 …), stages 는 단계들이다.
         *     cooling_until 은 다시 고백할 수 있는 시각(1일째 0시부터의 분)이고, 대기가 아니면 null 이다.
         *     gifts 는 이 가지에서 이 인물에게 건넨 물건(물건의 id)이다.
         */
        CastAffectionOut: {
            /** Cooling Until */
            cooling_until: number | null;
            /** Display */
            display: string;
            /** Gifts */
            gifts: string[];
            /** Stages */
            stages: components["schemas"]["StageOut"][];
        };
        /**
         * CastOut
         * @description 보이는 인물 하나. reveal 은 지금 보이는 법이다(만나면 shown).
         *     silhouette 이면 이름, 그림, 인물 창의 칸이 모두 null 이거나 비어 있다. 숨김인 인물은 만나기 전에는 목록에 없다.
         *     intro_html, age, gender, affection 은 제작자가 인물 창에 고른 항목만 실린다(아니면 null).
         *     events 는 이 가지에서 이 인물이 나온 이벤트(이벤트의 id)다. 호감도를 보이는 인물만 실린다.
         */
        CastOut: {
            affection: components["schemas"]["CastAffectionOut"] | null;
            /** Age */
            age: string | null;
            /** Confessable */
            confessable: boolean;
            /** Events */
            events: string[];
            /** Gender */
            gender: string | null;
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string | null;
            /** Met */
            met: boolean;
            /** Name */
            name: string | null;
            /** Reveal */
            reveal: string;
            /** Sprites */
            sprites: components["schemas"]["SpriteOut"][];
        };
        /**
         * ChoiceOut
         * @description 선택지 하나.
         */
        ChoiceOut: {
            /** Id */
            id: string;
            /** Text */
            text: string;
        };
        /**
         * ChooseAction
         * @description 기다리는 이벤트의 선택지 하나를 고른다.
         */
        ChooseAction: {
            /** Choice */
            choice: string;
            /**
             * Kind
             * @constant
             */
            kind: "choose";
        };
        /**
         * ConfessAction
         * @description 장면에 있는 인물 하나에게 고백한다. 성공과 실패는 엔진이 정한다.
         */
        ConfessAction: {
            /** Cast */
            cast: string;
            /**
             * Kind
             * @constant
             */
            kind: "confess";
        };
        /**
         * ContextMessageOut
         * @description 신고에 굳힌 앞의 말 하나. role 은 user, assistant, action 이다.
         */
        ContextMessageOut: {
            /** Content */
            content: string;
            /** Role */
            role: string;
        };
        /**
         * ConversationCreate
         * @description 세션을 시작할 때 받는 값. 세계관을 고른다. 그 세계관의 마지막 판을 가져와 고정한다.
         *
         *     persona_id 는 셋 중 하나다(chat 과 같다).
         *       - 보내지 않으면: 지난번 세션의 페르소나를 쓴다. 지난번에 없었거나 그 페르소나가 지워졌으면 페르소나 없이 시작한다
         *       - null 을 보내면: 페르소나 없이 시작한다
         *       - id 를 보내면: 그 계정 페르소나다. 없거나 남의 것이면 404 persona_not_found 다
         *
         *     model 도 셋 중 하나다(chat 과 같다).
         *       - 보내지 않으면: 지난번 세션의 모델을 쓴다. 지난번에 없었거나 이 세션에 고를 수 없으면 모델 없이 시작한다
         *       - null 을 보내면: 모델 없이 시작한다. 말을 보내기 전에 고른다
         *       - 이름표를 보내면: 그 모델이다. 이 세션에 고를 수 없으면 422 model_unavailable 이다
         */
        ConversationCreate: {
            /** Model */
            model?: string | null;
            /** Persona Id */
            persona_id?: string | null;
            /**
             * World Id
             * Format: uuid
             */
            world_id: string;
        };
        /**
         * ConversationDetail
         * @description 세션 하나. messages 는 지금 보고 있는 가지의 말들이다(첫 말부터, 말마다 대안들). state 는 그 끝의 상태다.
         */
        ConversationDetail: {
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
            /** Messages */
            messages: components["schemas"]["PathMessageOut"][];
            model: components["schemas"]["ConversationModelOut"] | null;
            persona?: components["schemas"]["PersonaOut"] | null;
            state: components["schemas"]["StateOut"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            view: components["schemas"]["WorldView"];
            world: components["schemas"]["WorldSummary"];
        };
        /**
         * ConversationModelOut
         * @description 세션에 싣는 모델. usable 이 거짓이면 이 세션에 더는 고를 수 없는 모델이다
         *     (꺼졌다, 은퇴했다, 성인 등급의 세션에 쓸 수 없게 됐다). 화면이 다시 고르게 한다. 서버는 몰래 바꾸지 않는다.
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
         * @description 목록의 한 쪽과 전체 개수. chat 의 GET /conversations 와 같은 모양이다(#593).
         */
        ConversationPage: {
            /** Items */
            items: components["schemas"]["ConversationSummary"][];
            /** Total */
            total: number;
        };
        /**
         * ConversationSummary
         * @description 목록의 한 줄. progress 는 지금 가지의 끝까지 온 곳이다.
         */
        ConversationSummary: {
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
            progress: components["schemas"]["ProgressOut"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            world: components["schemas"]["WorldSummary"];
        };
        /**
         * EndDayAction
         * @description 하루를 마치고 다음 날의 첫 시간대로.
         */
        EndDayAction: {
            /**
             * Kind
             * @constant
             */
            kind: "end_day";
        };
        /**
         * EndingOut
         * @description 엔딩의 칸 하나. 본 엔딩(계정의 기록이나 이 가지에서 본 것)만 이름과 일러스트가 실린다(아니면 null).
         *     hint 는 제작자가 적은 힌트다. unlock 이 거짓이면 계정에 남지 않는 엔딩이다(엔딩 수에 넣지 않는다).
         */
        EndingOut: {
            /** Hint */
            hint: string;
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string | null;
            /** Seen */
            seen: boolean;
            /** Unlock */
            unlock: boolean;
        };
        /**
         * EndingRecordList
         * @description 한 세계관에서 본 엔딩들. 처음 본 차례다.
         */
        EndingRecordList: {
            /** Items */
            items: components["schemas"]["EndingRecordOut"][];
        };
        /**
         * EndingRecordOut
         * @description 본 엔딩 하나. ending_id 는 판의 엔딩의 id 다. 이름과 힌트는 판의 문서에 있다.
         */
        EndingRecordOut: {
            /** Conversation Id */
            conversation_id: string | null;
            /** Ending Id */
            ending_id: string;
            /**
             * First Seen At
             * Format: date-time
             */
            first_seen_at: string;
        };
        /**
         * EventOut
         * @description 이 가지에서 열린 이벤트 하나. cast 는 장면이 부른 인물, image_id 는 장면의 일러스트다.
         *     choices 는 고르기를 기다리는 이벤트에만 실린다(아니면 빈 목록). 열리는 조건과 효과는 싣지 않는다.
         */
        EventOut: {
            /** Cast */
            cast: string[];
            /** Choices */
            choices: components["schemas"]["ChoiceOut"][];
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string;
        };
        /**
         * GiveAction
         * @description 장면에 있는 인물 하나에게 가진 물건 하나를 건넨다. 호감도가 얼마나 바뀌는지는 엔진이 정한다.
         */
        GiveAction: {
            /** Cast */
            cast: string;
            /** Item */
            item: string;
            /**
             * Kind
             * @constant
             */
            kind: "give";
        };
        /**
         * Grade
         * @description 보이는 분류. 목록을 묶어 보이는 데만 쓴다. 값은 모델마다 모델 목록의 파일에 적는다.
         * @enum {string}
         */
        Grade: "basic" | "standard" | "premium";
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /**
         * IllustrationList
         * @description 한 세계관에서 연 일러스트들. 처음 연 차례다.
         */
        IllustrationList: {
            /** Items */
            items: components["schemas"]["IllustrationOut"][];
        };
        /**
         * IllustrationOut
         * @description 연 일러스트 하나. 장면은 종류(event, ending)와 판의 id 다. image_id 는 연 때의 그림이다.
         *     cast 는 그 장면이 부르는 인물들이다. 갤러리는 인물마다 묶고, 비었으면 세계관 칸에 둔다.
         */
        IllustrationOut: {
            /** Cast */
            cast: string[];
            /** Conversation Id */
            conversation_id: string | null;
            /**
             * First Seen At
             * Format: date-time
             */
            first_seen_at: string;
            /**
             * Image Id
             * Format: uuid
             */
            image_id: string;
            kind: components["schemas"]["SceneKind"];
            /** Scene Id */
            scene_id: string;
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
         * ItemOut
         * @description 물건 하나.
         */
        ItemOut: {
            /** Consumable */
            consumable: boolean;
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
         * MapPlaceOut
         * @description 지도의 장소 하나(D3). visited 는 이 가지에서 가 본 곳인가다.
         *     cast 는 지금 거기 있는 것이 보이는 인물들이다: 가 본 곳이고, 만난 적이 있고, 제작자의 지도 보이기를 통과한 인물.
         *     함께 다니는 인물은 넣지 않는다(상태의 companions 로 내 자리 옆에 보인다).
         */
        MapPlaceOut: {
            /** Cast */
            cast: string[];
            /** Id */
            id: string;
            /** Visited */
            visited: boolean;
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
         * @description 답을 고친 글. 조각마다 고친 글을 차례대로 적는다. 조각의 수는 그 답의 것과 같아야 한다.
         *     말하는 사람은 보내지 않는다. 저장된 그대로다(장면 밖의 인물이 끼어들 길이 없다).
         */
        MessageEdit: {
            /** Segments */
            segments: string[];
        };
        /**
         * MessageOut
         * @description 말 하나. role 은 user(사람의 말), assistant(모델의 답), action(사람의 행동)이다.
         *     모델의 답은 segments(말 조각)를 그린다. content 는 그 조각을 표식이 붙은 줄로 쓴 것이다.
         *     cast 는 그 답을 쓸 때의 장면의 인물이다. status 가 partial 이면 끊긴 답이다.
         */
        MessageOut: {
            /** Cast */
            cast: string[];
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
            /** Ending Id */
            ending_id?: string | null;
            /** Event Id */
            event_id?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Role */
            role: string;
            /** Segments */
            segments: components["schemas"]["SegmentOut"][];
            /** Status */
            status: string;
            /** Suggestions */
            suggestions?: string[];
        };
        /**
         * ModelChoice
         * @description 세션의 모델을 바꿀 때 받는 값.
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
         * @description 지금 장소와 길로 바로 이어진 장소로 옮긴다. 길의 시간만큼 시각이 흐른다.
         */
        MoveAction: {
            /**
             * Kind
             * @constant
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
         * @description 메모 하나(chat 과 같은 모양). source 는 누가 썼는가(user, summary)다. pending 이면 요약의 제안이고 받아들이기 전이다
         *     (모델에 가지 않는다. 화면은 받아들이기와 버리기를 보인다). accepted_at 은 제안을 받아들인 시각이다.
         */
        NoteOut: {
            /** Accepted At */
            accepted_at: string | null;
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
            /** Pending */
            pending: boolean;
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
         * @description 메모를 쓰거나 고칠 때 받는 글. 앞뒤 빈칸은 걷는다.
         */
        NoteWrite: {
            /** Text */
            text: string;
        };
        /**
         * OutcomeInput
         * @description 신고의 처리. reason 은 감사 기록의 사유다. 처리는 기록일 뿐 세계관을 숨기지 않는다.
         */
        OutcomeInput: {
            outcome: components["schemas"]["ReportOutcome"];
            /** Reason */
            reason: string;
        };
        /**
         * PassTimeAction
         * @description 다음 시간대로.
         */
        PassTimeAction: {
            /**
             * Kind
             * @constant
             */
            kind: "pass_time";
        };
        /**
         * PathMessageOut
         * @description 지금 가지의 말 하나와 그 대안들. alternatives 는 같은 부모 아래의 말들의 id 다(먼저 생긴 것부터, 이 말도 든다).
         *
         *     화면이 "< 2/3 >" 를 그리고, 다른 대안을 고르면 PUT /conversations/{id}/branch 로 그 가지를 본다(chat 과 같다).
         */
        PathMessageOut: {
            /** Alternatives */
            alternatives: string[];
            /** Cast */
            cast: string[];
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
            /** Ending Id */
            ending_id?: string | null;
            /** Event Id */
            event_id?: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Parent Id */
            parent_id: string | null;
            /** Role */
            role: string;
            /** Segments */
            segments: components["schemas"]["SegmentOut"][];
            /** Status */
            status: string;
            /** Suggestions */
            suggestions?: string[];
        };
        /**
         * PathOut
         * @description 두 장소를 잇는 길과 걸리는 분.
         */
        PathOut: {
            /** A */
            a: string;
            /** B */
            b: string;
            /** Minutes */
            minutes: number;
        };
        /**
         * PersonaChoice
         * @description 세션의 페르소나를 바꿀 때 받는 값. persona_id 는 꼭 보낸다.
         *       - id 를 보내면: 그 계정 페르소나의 지금 것을 가져와 바꾼다. 같은 id 면 새 설정으로 바꾸는 것이다
         *       - null 을 보내면: 페르소나 없이 이어 간다
         */
        PersonaChoice: {
            /** Persona Id */
            persona_id: string | null;
        };
        /**
         * PersonaChoiceOut
         * @description 바꾼 뒤의 세션의 페르소나. 없이 이어 가면 null 이다.
         */
        PersonaChoiceOut: {
            persona: components["schemas"]["PersonaOut"] | null;
        };
        /**
         * PersonaOut
         * @description 세션에 가져온 페르소나의 사본(chat 과 같은 모양). id 는 asset 서버의 페르소나 id 다.
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
         * PlaceOut
         * @description 장소 하나. backgrounds 는 시간대의 id 마다의 배경 그림이다.
         */
        PlaceOut: {
            /** Backgrounds */
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
         * ProgressOut
         * @description 세션의 지금 가지의 끝까지 온 곳. 목록(D1 의 내 세션)이 날짜와 진행, 끝, 후일담을 그린다.
         *     day 는 며칠째, slot 은 시간대의 id, deadline_days 는 판의 기한(없으면 null)이다. 남은 날은 deadline_days - day 다.
         *     ending 은 이 가지에서 본 엔딩의 id 와 이름(못 봤으면 null)이다.
         *     epilogue 는 엔딩을 봤고 세계관이 후일담을 골라 이야기가 이어지는 것이다(엔딩을 봤는데 거짓이면 끝난 세션이다).
         */
        ProgressOut: {
            /** Day */
            day: number;
            /** Deadline Days */
            deadline_days: number | null;
            /** Ending */
            ending: string | null;
            /** Ending Name */
            ending_name: string | null;
            /** Epilogue */
            epilogue: boolean;
            /** Slot */
            slot: string;
        };
        /**
         * Rating
         * @description 이용 등급. asset 서버, chat 서버, 게임 서버와 같은 값이다.
         * @enum {string}
         */
        Rating: "all" | "adult";
        /**
         * ReportCreate
         * @description 신고할 때 받는 값. 사유가 other 면 설명이 있어야 한다(asset 의 신고와 같다).
         */
        ReportCreate: {
            /**
             * Description
             * @default
             */
            description: string;
            reason: components["schemas"]["ReportReason"];
        };
        /**
         * ReportCreated
         * @description 접수한 신고.
         */
        ReportCreated: {
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
        };
        /**
         * ReportDetailOut
         * @description 신고 하나와 굳힌 글. 볼 때마다 감사 기록에 남는다.
         */
        ReportDetailOut: {
            /** Content */
            content: string;
            /** Context */
            context: components["schemas"]["ContextMessageOut"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** Handled At */
            handled_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Model Slug */
            model_slug: string | null;
            outcome: components["schemas"]["ReportOutcome"] | null;
            reason: components["schemas"]["ReportReason"];
            /**
             * World Id
             * Format: uuid
             */
            world_id: string;
            /** World Name */
            world_name: string;
            /** World Version */
            world_version: number;
        };
        /**
         * ReportOutcome
         * @description 처리의 결과. 받아들였다, 받아들이지 않았다. 처리는 기록일 뿐 세계관을 숨기지 않는다.
         * @enum {string}
         */
        ReportOutcome: "actioned" | "dismissed";
        /**
         * ReportPage
         * @description 열린 신고의 한 쪽과 전체 수.
         */
        ReportPage: {
            /** Items */
            items: components["schemas"]["ReportSummaryOut"][];
            /** Total */
            total: number;
        };
        /**
         * ReportReason
         * @description 신고의 사유. asset 의 신고와 같다. minor 는 운영자의 목록에서 가장 먼저 보인다.
         * @enum {string}
         */
        ReportReason: "spam" | "abuse" | "sexual" | "minor" | "illegal" | "other";
        /**
         * ReportSummaryOut
         * @description 열린 신고의 한 줄. 세션의 글은 싣지 않는다(열어 볼 때 감사 기록과 함께 준다). 신고한 사람의 id 도 없다.
         */
        ReportSummaryOut: {
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
            /** Model Slug */
            model_slug: string | null;
            reason: components["schemas"]["ReportReason"];
            /**
             * World Id
             * Format: uuid
             */
            world_id: string;
            /** World Name */
            world_name: string;
            /** World Version */
            world_version: number;
        };
        /**
         * SceneKind
         * @description 일러스트가 붙은 장면의 종류. 이벤트와 엔딩의 id 는 서로 겹칠 수 있어 종류로 가른다.
         * @enum {string}
         */
        SceneKind: "event" | "ending";
        /**
         * SegmentOut
         * @description 말 조각 하나. speaker 는 장면의 인물의 id(판의 cast 의 id)이고, 서술이면 null 이다.
         *     expression 은 그 줄에서 모델이 고른 표정(그 인물의 그림의 표정 이름)이다. 기본 표정이거나 서술이면 null 이다.
         */
        SegmentOut: {
            /** Expression */
            expression?: string | null;
            /** Speaker */
            speaker: string | null;
            /** Text */
            text: string;
        };
        /**
         * SlotOut
         * @description 시간대 하나. start_hour 부터 다음 시간대가 시작할 때까지다.
         */
        SlotOut: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Start Hour */
            start_hour: number;
        };
        /**
         * SpriteOut
         * @description 인물의 그림 하나. expression 은 표정(빈 글이면 기본)이다.
         */
        SpriteOut: {
            /** Expression */
            expression: string;
            /** Id */
            id: string;
            /**
             * Image Id
             * Format: uuid
             */
            image_id: string;
        };
        /**
         * StageOut
         * @description 호감도의 단계 하나. at 이상이면 이 단계다.
         */
        StageOut: {
            /** At */
            at: number;
            /** Name */
            name: string;
        };
        /**
         * StateOut
         * @description 가지의 끝의 상태(엔진의 상태). 화면이 시계, 지도, 소지품, 인물 창, 선택지, 엔딩을 그린다.
         *
         *     minutes 는 1일째 0시부터 흐른 분이고, day 와 slot(시간대의 id)은 그 수에서 계산한 것이다.
         *     affection 은 인물마다의 호감도(0~100)다. 인물 창에 호감도를 보이는 인물만 실린다
         *     (view 의 cast 에 affection 이 있는 인물).
         *     숫자로 보일지 단계로 보일지는 view 의 affection.display 를 따라 화면이 정한다.
         *     choosing 은 선택지를 기다리는 이벤트, ending 은 이 가지에서 본 엔딩이다. cast 는 지금 장소의 장면의 인물이다.
         */
        StateOut: {
            /** Affection */
            affection: {
                [key: string]: number;
            };
            /** Cast */
            cast: string[];
            /** Choosing */
            choosing: string | null;
            /** Companions */
            companions: string[];
            /** Day */
            day: number;
            /** Ending */
            ending: string | null;
            /** Items */
            items: {
                [key: string]: number;
            };
            /** Minutes */
            minutes: number;
            /** Place */
            place: string;
            /** Slot */
            slot: string;
        };
        /**
         * SummaryOut
         * @description 지금 가지의 굴리는 요약(읽기만). covered_up_to 는 요약한 마지막 말의 id 다(첫 말부터 그 말까지를 요약했다).
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
         *     그래서 결제 서버는 게임 서버와 chat, story 서버가 등급을 안 뒤에 그 줄을 넣는다.
         * @enum {string}
         */
        Tier: "basic" | "standard" | "premium";
        /**
         * TranscriptFormat
         * @description 기록의 형식.
         * @enum {string}
         */
        TranscriptFormat: "md" | "html" | "txt";
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
        /**
         * WorldSummary
         * @description 목록에 싣는 세계관. id 는 asset 서버의 세계관 id 이고 version 은 이 세션이 쓰는 판의 번호다.
         *     genre 는 판의 장르다(화면이 장면의 테마를 고른다). 늘 있다. 사본에 없으면 기본 장르다(app/conversations/genres.py).
         */
        WorldSummary: {
            /** Genre */
            genre: string;
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
         * WorldView
         * @description 세션에서 화면이 쓰는 세계관의 칸. 판의 문서에서 지금 보여도 되는 것만 골라 이 가지의 상태에 맞춘다.
         *     이벤트와 엔딩의 조건, 일정, 호감도의 규칙, 만나지 않은 인물은 싣지 않는다.
         */
        WorldView: {
            /** After Ending */
            after_ending: string;
            /** Cast */
            cast: components["schemas"]["CastOut"][];
            /** Deadline Days */
            deadline_days: number | null;
            /** Endings */
            endings: components["schemas"]["EndingOut"][];
            /** Events */
            events: components["schemas"]["EventOut"][];
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
            /** Items */
            items: components["schemas"]["ItemOut"][];
            /** Map */
            map: components["schemas"]["MapPlaceOut"][];
            /** Name */
            name: string;
            /** Paths */
            paths: components["schemas"]["PathOut"][];
            /** Places */
            places: components["schemas"]["PlaceOut"][];
            /** Slots */
            slots: components["schemas"]["SlotOut"][];
            /** Tags */
            tags: string[];
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
    list_reports_api_v1_story_admin_message_reports_get: {
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
                    "application/json": components["schemas"]["ReportPage"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_report_api_v1_story_admin_message_reports__report_id__get: {
        parameters: {
            query: {
                reason: string;
            };
            header?: never;
            path: {
                report_id: string;
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
                    "application/json": components["schemas"]["ReportDetailOut"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    handle_report_api_v1_story_admin_message_reports__report_id__outcome_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OutcomeInput"];
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
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_conversations_api_v1_story_conversations_get: {
        parameters: {
            query?: {
                /** @description asset 서버의 세계관 id. 주면 그 세계관의 세션만 */
                world_id?: string | null;
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    start_conversation_api_v1_story_conversations_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_conversation_api_v1_story_conversations__conversation_id__get: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    delete_conversation_api_v1_story_conversations__conversation_id__delete: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    act_api_v1_story_conversations__conversation_id__actions_post: {
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
                "application/json": components["schemas"]["MoveAction"] | components["schemas"]["PassTimeAction"] | components["schemas"]["EndDayAction"] | components["schemas"]["ChooseAction"] | components["schemas"]["ConfessAction"] | components["schemas"]["GiveAction"];
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    choose_branch_api_v1_story_conversations__conversation_id__branch_put: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    send_message_api_v1_story_conversations__conversation_id__messages_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    change_model_api_v1_story_conversations__conversation_id__model_put: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_notes_api_v1_story_conversations__conversation_id__notes_get: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    add_note_api_v1_story_conversations__conversation_id__notes_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    delete_note_api_v1_story_conversations__conversation_id__notes__note_id__delete: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    edit_note_api_v1_story_conversations__conversation_id__notes__note_id__patch: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    accept_note_api_v1_story_conversations__conversation_id__notes__note_id__accept_post: {
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
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoteOut"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    change_persona_api_v1_story_conversations__conversation_id__persona_put: {
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
                "application/json": components["schemas"]["PersonaChoice"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaChoiceOut"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_summary_api_v1_story_conversations__conversation_id__summary_get: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    download_transcript_api_v1_story_conversations__conversation_id__transcript_get: {
        parameters: {
            query?: {
                format?: components["schemas"]["TranscriptFormat"];
            };
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
                    "text/html": unknown;
                    "text/markdown": unknown;
                    "text/plain": unknown;
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_endings_api_v1_story_endings_get: {
        parameters: {
            query: {
                /** @description asset 서버의 세계관 id */
                world_id: string;
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
                    "application/json": components["schemas"]["EndingRecordList"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_illustrations_api_v1_story_gallery_get: {
        parameters: {
            query: {
                /** @description asset 서버의 세계관 id */
                world_id: string;
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
                    "application/json": components["schemas"]["IllustrationList"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    stop_generation_api_v1_story_generations__generation_id__stop_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    read_me_api_v1_story_me_get: {
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
    edit_message_api_v1_story_messages__message_id__patch: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    continue_message_api_v1_story_messages__message_id__continue_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    regenerate_api_v1_story_messages__message_id__regenerate_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    report_message_api_v1_story_messages__message_id__reports_post: {
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
                "application/json": components["schemas"]["ReportCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportCreated"];
                };
            };
            /** @description 입력이 틀렸다 */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InputError"];
                };
            };
        };
    };
    list_models_api_v1_story_models_get: {
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
    receive_withdrawal_api_v1_story_service_users__public_id__withdrawal_post: {
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
            /** @description 입력이 틀렸다 */
            422: {
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
