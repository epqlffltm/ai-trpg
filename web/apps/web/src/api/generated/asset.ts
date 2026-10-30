// web/apps/web/src/api/generated/asset.ts
// docs/api/asset.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/asset/admin/character-reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Open Reports
         * @description 열린 신고를 캐릭터마다 묶은 목록. minor 가 있는 것이 먼저, 그다음 마지막 신고가 최근인 것부터다.
         */
        get: operations["list_open_reports_api_v1_asset_admin_character_reports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/admin/characters/{character_id}/hidden": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Hidden
         * @description 캐릭터를 숨기거나 푼다. 캐릭터가 없으면 404 다.
         */
        put: operations["change_hidden_api_v1_asset_admin_characters__character_id__hidden_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/admin/characters/{character_id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Character Reports
         * @description 그 캐릭터의 신고 전부(처리된 것까지). 최근 것부터. 캐릭터가 없으면 404 다.
         */
        get: operations["list_character_reports_api_v1_asset_admin_characters__character_id__reports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/admin/characters/{character_id}/reports/outcome": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Handle Reports
         * @description 그 캐릭터의 열린 신고를 처리한다. actioned 면 숨기고, dismissed 면 그대로 둔다. 캐릭터가 없으면 404 다.
         */
        put: operations["handle_reports_api_v1_asset_admin_characters__character_id__reports_outcome_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/admin/worlds/{world_id}/hidden": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change World Hidden
         * @description 세계관을 숨기거나 푼다. 세계관이 없으면 404 다. story 의 신고(world_id)를 보고 한다.
         */
        put: operations["change_world_hidden_api_v1_asset_admin_worlds__world_id__hidden_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
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
         * @description 자기 캐릭터의 초안을 고친다. 보낸 칸만 바뀐다. 공개로 두는 것은 운영자만이다(PUBLIC_FOR_EVERYONE 이면 누구나).
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
    "/api/v1/asset/listings/characters/{character_id}/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Report Character
         * @description 공개 캐릭터를 신고한다. 볼 수 없는 캐릭터는 404, 자기 것은 403, 이미 신고했으면 409 다.
         */
        post: operations["report_character_api_v1_asset_listings_characters__character_id__reports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/listings/worlds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Public
         * @description 공개 세계관의 목록. 최근에 게시한 것부터다.
         */
        get: operations["list_public_api_v1_asset_listings_worlds_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/listings/worlds/{world_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Public
         * @description 공개 세계관의 소개. 볼 수 없으면 404 다.
         */
        get: operations["read_public_api_v1_asset_listings_worlds__world_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/lorebooks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Lorebooks
         * @description 자기 로어북의 목록. 최근에 고친 것부터다.
         */
        get: operations["list_lorebooks_api_v1_asset_lorebooks_get"];
        put?: never;
        /**
         * Create Lorebook
         * @description 로어북을 만든다. 1~2단계에는 운영자만 만든다(403 operator_only).
         */
        post: operations["create_lorebook_api_v1_asset_lorebooks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/lorebooks/{lorebook_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Lorebook
         * @description 자기 로어북의 초안 하나.
         */
        get: operations["read_lorebook_api_v1_asset_lorebooks__lorebook_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Lorebook
         * @description 자기 로어북을 지운다. 판도 함께 지워진다. 게시한 캐릭터의 판에 복사된 것은 남는다.
         */
        delete: operations["delete_lorebook_api_v1_asset_lorebooks__lorebook_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Lorebook
         * @description 자기 로어북의 초안을 고친다. 보낸 칸만 바뀐다. 항목은 목록을 통째로 바꾼다.
         */
        patch: operations["update_lorebook_api_v1_asset_lorebooks__lorebook_id__patch"];
        trace?: never;
    };
    "/api/v1/asset/lorebooks/{lorebook_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Versions
         * @description 자기 로어북의 판들. 최근 것부터다.
         */
        get: operations["list_versions_api_v1_asset_lorebooks__lorebook_id__versions_get"];
        put?: never;
        /**
         * Publish
         * @description 게시한다. 새 판을 돌려준다.
         */
        post: operations["publish_api_v1_asset_lorebooks__lorebook_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/lorebooks/{lorebook_id}/versions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Version
         * @description 자기 로어북의 판 하나. 굳힌 문서까지다.
         */
        get: operations["read_version_api_v1_asset_lorebooks__lorebook_id__versions__number__get"];
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
    "/api/v1/asset/service/{caller}/worlds/{world_id}/latest": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Copy Latest
         * @description 토큰의 주인이 쓸 수 있는 세계관의 마지막 판.
         */
        get: operations["copy_latest_api_v1_asset_service__caller__worlds__world_id__latest_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/service/{caller}/worlds/{world_id}/latest/number": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Latest Number
         * @description 토큰의 주인이 쓸 수 있는 세계관의 마지막 판의 번호.
         */
        get: operations["read_latest_number_api_v1_asset_service__caller__worlds__world_id__latest_number_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/worlds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Worlds
         * @description 자기 세계관의 목록. 최근에 고친 것부터다.
         */
        get: operations["list_worlds_api_v1_asset_worlds_get"];
        put?: never;
        /**
         * Create World
         * @description 세계관을 만든다. 처음에는 비공개다. 1~2단계에는 운영자만 만든다(403 operator_only).
         */
        post: operations["create_world_api_v1_asset_worlds_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/worlds/{world_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read World
         * @description 자기 세계관의 초안 하나.
         */
        get: operations["read_world_api_v1_asset_worlds__world_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete World
         * @description 자기 세계관을 지운다. 판도 함께 지워진다.
         */
        delete: operations["delete_world_api_v1_asset_worlds__world_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update World
         * @description 자기 세계관의 초안을 고친다. 보낸 칸만 바뀐다. 공개로 두는 것은 운영자만이다(PUBLIC_FOR_EVERYONE 이면 누구나).
         */
        patch: operations["update_world_api_v1_asset_worlds__world_id__patch"];
        trace?: never;
    };
    "/api/v1/asset/worlds/{world_id}/publish-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Check Publish
         * @description 게시해 보기. 막히는 이유, 알리는 것, 소개에서 걸러질 것을 본다. 판은 생기지 않는다.
         */
        get: operations["check_publish_api_v1_asset_worlds__world_id__publish_check_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/worlds/{world_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Versions
         * @description 자기 세계관의 판들. 최근 것부터다.
         */
        get: operations["list_versions_api_v1_asset_worlds__world_id__versions_get"];
        put?: never;
        /**
         * Publish
         * @description 게시한다. 새 판과 소개에서 걸러 낸 것들, 알리는 것들을 돌려준다. 막는 것이 있으면 409 다.
         */
        post: operations["publish_api_v1_asset_worlds__world_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/asset/worlds/{world_id}/versions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Version
         * @description 자기 세계관의 판 하나. 굳힌 문서까지다.
         */
        get: operations["read_version_api_v1_asset_worlds__world_id__versions__number__get"];
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
             * Model Step
             * @default 3
             */
            model_step: number;
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
            /**
             * Model Step
             * @default 3
             */
            model_step: number;
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
            on: components["schemas"]["app__characters__schemas__Trigger"];
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
            on: components["schemas"]["app__characters__documents__TriggerDocument"];
            /** Once */
            once: boolean;
        };
        /**
         * AfterEnding
         * @description 엔딩 뒤에 세션이 어떻게 되는가(story.md 의 "세션과 기록"). 끝(읽기만) 또는 후일담.
         * @enum {string}
         */
        AfterEnding: "end" | "epilogue";
        /**
         * CastAffection
         * @description 인물의 호감도. 값 하나(0~100)와 단계들이다. chat 의 호감도와 보이는 방식과 단계가 같다.
         *     바뀌는 길은 선물의 규칙과 이벤트의 효과(두 번째 조각)다. 대화의 내용만으로는 움직이지 않는다(story.md 의 "호감도").
         */
        CastAffection: {
            /** @default number */
            display: components["schemas"]["AffectionDisplay"];
            /**
             * Gifts
             * @default []
             */
            gifts: components["schemas"]["Gift"][];
            /** Stages */
            stages: components["schemas"]["Stage"][];
            /**
             * Start
             * @default 0
             */
            start: number;
        };
        /**
         * CastAffectionDocument
         * @description 인물의 호감도.
         */
        CastAffectionDocument: {
            display: components["schemas"]["AffectionDisplay"];
            /** Gifts */
            gifts: components["schemas"]["GiftDocument"][];
            /** Stages */
            stages: components["schemas"]["StageDocument"][];
            /** Start */
            start: number;
        };
        /**
         * CastCharacterDocument
         * @description 인물에 복사한 캐릭터. id 와 version 은 캐릭터와 그 판의 번호다(어디서 왔는지 적어 둔다).
         *     캐릭터의 판 가운데 story 에 쓰는 칸만이다. intro_html 은 캐릭터를 게시할 때 거른 것이다.
         */
        CastCharacterDocument: {
            /** Age */
            age: string;
            /** Gender */
            gender: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
            /** Name */
            name: string;
            /** Speech Examples */
            speech_examples: string;
            /** Sprites */
            sprites: components["schemas"]["SpriteDocument"][];
            /** Version */
            version: number;
        };
        /**
         * CastDocument
         * @description 인물 하나. 보이기(reveal, map, panel)는 기본을 채운 정해진 값이다.
         */
        CastDocument: {
            affection: components["schemas"]["CastAffectionDocument"];
            character: components["schemas"]["CastCharacterDocument"];
            confession?: components["schemas"]["ConfessionDocument"] | null;
            /** Home */
            home: string | null;
            /** Id */
            id: string;
            map: components["schemas"]["MapPresence"];
            /** Map Stage */
            map_stage: string | null;
            /** Panel */
            panel: components["schemas"]["PanelField"][];
            reveal: components["schemas"]["Reveal"];
            /** Schedule */
            schedule: components["schemas"]["ScheduleLineDocument"][];
        };
        /**
         * CastMember
         * @description 인물 하나. character_id 는 만든 사람의 캐릭터다. 게시할 때 그 마지막 판의 story 에 쓰는 칸을 복사한다.
         *     id 는 세계관 안에서 고유하고 조건과 일정이 가리킨다. 판이 바뀌어도 같은 인물은 같은 id 로 둔다.
         *
         *     home 은 기본 장소다. 비우면 어디에도 없다(이벤트로만 나온다). schedule 은 기본 장소를 덮어쓰는 일정이다.
         *     reveal, map, panel 은 보이기의 덮어쓰기다. 비우면 세계관의 기본을 쓴다.
         *     map_stage 는 지도에 보이는 호감도의 단계다. 이 인물의 지도가 stage 일 때 쓴다.
         *     confession 은 고백이다(판의 형식 3). 비우면 고백할 수 없다.
         */
        CastMember: {
            affection: components["schemas"]["CastAffection"];
            /**
             * Character Id
             * Format: uuid
             */
            character_id: string;
            confession?: components["schemas"]["Confession"] | null;
            /** Home */
            home?: string | null;
            /** Id */
            id: string;
            map?: components["schemas"]["MapPresence"] | null;
            /** Map Stage */
            map_stage?: string | null;
            /** Panel */
            panel?: components["schemas"]["PanelField"][] | null;
            reveal?: components["schemas"]["Reveal"] | null;
            /**
             * Schedule
             * @default []
             */
            schedule: components["schemas"]["ScheduleLine"][];
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
             * Event Scenes
             * @default []
             */
            event_scenes: components["schemas"]["EventScene"][];
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
            /**
             * Lorebooks
             * @default []
             */
            lorebooks: string[];
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
             * Sprites
             * @default []
             */
            sprites: components["schemas"]["Sprite"][];
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
            /** Event Scenes */
            event_scenes: components["schemas"]["EventScene"][];
            /** Gender */
            gender: string;
            /** Greeting */
            greeting: string;
            /** Hidden At */
            hidden_at: string | null;
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
            /** Lorebooks */
            lorebooks: string[];
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
            /** Sprites */
            sprites: components["schemas"]["Sprite"][];
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
            /**
             * Lorebooks
             * @default []
             */
            lorebooks: components["schemas"]["LorebookCopyDocument"][];
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
            start_items: components["schemas"]["app__characters__documents__StartItemDocument"][];
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
            /** Hidden At */
            hidden_at: string | null;
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
            /** Event Scenes */
            event_scenes?: components["schemas"]["EventScene"][] | null;
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
            /** Lorebooks */
            lorebooks?: string[] | null;
            /** Name */
            name?: string | null;
            /** Paths */
            paths?: components["schemas"]["Path"][] | null;
            /** Places */
            places?: components["schemas"]["Place"][] | null;
            rating?: components["schemas"]["Rating"] | null;
            /** Speech Examples */
            speech_examples?: string | null;
            /** Sprites */
            sprites?: components["schemas"]["Sprite"][] | null;
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
        /**
         * Choice
         * @description 선택지 하나. 제작자가 적은 글과, 고르면 엔진이 반영하는 효과들이다. id 는 이벤트 안에서 고유하다.
         */
        Choice: {
            /**
             * Effects
             * @default []
             */
            effects: components["schemas"]["Effect"][];
            /** Id */
            id: string;
            /** Text */
            text: string;
        };
        /**
         * ChoiceDocument
         * @description 선택지 하나.
         */
        ChoiceDocument: {
            /** Effects */
            effects: components["schemas"]["EffectDocument"][];
            /** Id */
            id: string;
            /** Text */
            text: string;
        };
        /**
         * Condition
         * @description 조건 하나(story.md 의 "조건"). 종류(kind)마다 쓰는 칸이 다르다(CONDITION_FIELDS).
         *     target 은 장소, 물건, 인물, 시간대, 이벤트의 id 다. value 는 물건의 id(건넸다)나 호감도 단계의 이름이다.
         *     count 는 물건의 수(가졌다)나 날짜(n일째)다. 쓰지 않는 칸은 적지 않는다.
         */
        Condition: {
            /**
             * Count
             * @default 1
             */
            count: number;
            kind: components["schemas"]["ConditionKind"];
            /** Target */
            target?: string | null;
            /** Value */
            value?: string | null;
        };
        /**
         * ConditionDocument
         * @description 조건 하나. 종류마다 쓰는 칸이 다르다(app/worlds/models.py 의 ConditionKind).
         */
        ConditionDocument: {
            /** Count */
            count: number;
            kind: components["schemas"]["ConditionKind"];
            /** Target */
            target: string | null;
            /** Value */
            value: string | null;
        };
        /**
         * ConditionKind
         * @description 조건 하나가 무엇을 보는가(story.md 의 "조건"). 엔진(story 서버)이 이미 아는 사실만 본다.
         *
         *     종류마다 쓰는 칸이 정해져 있다(app/worlds/schemas.py 의 Condition).
         *       reach_place        target: 장소          사용자가 그 장소에 있다
         *       hold_item          target: 물건, count   그 물건을 count 개 이상 가졌다
         *       gave_item          target: 인물, value: 물건   그 인물에게 그 물건을 건넨 적이 있다
         *       affection_at_least target: 인물, value: 단계   그 인물의 호감도가 그 단계 이상이다
         *       affection_below    target: 인물, value: 단계   그 인물의 호감도가 그 단계보다 아래다
         *       day_at_least       count                 n일째 이상이다
         *       day_at_most        count                 n일째 이하다
         *       slot_is            target: 시간대        지금의 시간대가 그것이다
         *       accompanied        target: 인물          그 인물과 동행 중이다
         *       event_seen         target: 이벤트        그 이벤트가 열린 적이 있다(판의 형식 2)
         * @enum {string}
         */
        ConditionKind: "reach_place" | "hold_item" | "gave_item" | "affection_at_least" | "affection_below" | "day_at_least" | "day_at_most" | "slot_is" | "accompanied" | "event_seen";
        /**
         * Conditions
         * @description 조건 목록과 맞추는 법. 목록이 비면 늘 맞는다.
         */
        Conditions: {
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["Condition"][];
            /** @default all */
            match: components["schemas"]["Match"];
        };
        /**
         * ConditionsDocument
         * @description 조건 목록과 맞추는 법. 목록이 비면 늘 맞는다.
         */
        ConditionsDocument: {
            /** Items */
            items: components["schemas"]["ConditionDocument"][];
            match: components["schemas"]["Match"];
        };
        /**
         * Confession
         * @description 인물에게 하는 고백(story.md 의 "고백과 엔딩"). 호감도가 stage(단계의 이름) 이상이고 when 이 맞으면 성공이다.
         *     실패하면 on_fail 대로 한다. 계속(continue)이면 호감도를 fail_drop 만큼 내리고 cooldown_days 동안 다시 못 한다.
         *     끝(end)이면 그 인물에게 고백 실패로 시작되는 엔딩을 판정한다. 비어 있으면(null) 고백할 수 없는 인물이다.
         */
        Confession: {
            /**
             * Cooldown Days
             * @default 1
             */
            cooldown_days: number;
            /**
             * Fail Drop
             * @default 10
             */
            fail_drop: number;
            /** @default continue */
            on_fail: components["schemas"]["ConfessionFailure"];
            /** Stage */
            stage: string;
            /**
             * @default {
             *       "items": [],
             *       "match": "all"
             *     }
             */
            when: components["schemas"]["Conditions"];
        };
        /**
         * ConfessionDocument
         * @description 인물에게 하는 고백. stage 이상이고 when 이 맞으면 성공이다.
         */
        ConfessionDocument: {
            /** Cooldown Days */
            cooldown_days: number;
            /** Fail Drop */
            fail_drop: number;
            on_fail: components["schemas"]["ConfessionFailure"];
            /** Stage */
            stage: string;
            when: components["schemas"]["ConditionsDocument"];
        };
        /**
         * ConfessionFailure
         * @description 고백에 실패하면 어떻게 되는가. 계속(호감도가 내려가고 정한 날 동안 다시 못 한다) 또는 실패 엔딩으로 끝.
         * @enum {string}
         */
        ConfessionFailure: "continue" | "end";
        /**
         * Effect
         * @description 효과 하나(story.md 의 "효과"). target 은 인물, 물건, 장소의 id 다(종류마다, EffectKind).
         *     amount 는 호감도를 바꾸는 크기(±, 0 이 아니다)나 주고 가져가는 물건의 수(1 이상)다. 쓰지 않는 종류는 적지 않는다.
         */
        Effect: {
            /** Amount */
            amount?: number | null;
            kind: components["schemas"]["EffectKind"];
            /** Target */
            target: string;
        };
        /**
         * EffectDocument
         * @description 효과 하나. amount 는 호감도의 크기나 물건의 수다(쓰지 않는 종류는 null).
         */
        EffectDocument: {
            /** Amount */
            amount: number | null;
            kind: components["schemas"]["EffectKind"];
            /** Target */
            target: string;
        };
        /**
         * EffectKind
         * @description 효과 하나가 무엇을 바꾸는가(story.md 의 "효과"). 엔진(story 서버)만 반영한다. 모델의 글에는 효과가 없다.
         *
         *     종류마다 쓰는 칸이 정해져 있다(app/worlds/schemas.py 의 Effect).
         *       affection        target: 인물, amount: ±n   그 인물의 호감도를 바꾼다(0~100 안으로 자른다)
         *       give_item        target: 물건, amount: n    사용자에게 그 물건을 준다
         *       take_item        target: 물건, amount: n    사용자에게서 그 물건을 가져간다(가진 만큼까지)
         *       accompany_start  target: 인물               그 인물과 동행을 시작한다
         *       accompany_end    target: 인물               그 인물과 동행을 끝낸다
         *       move_to          target: 장소               사용자(와 동행)를 그 장소로 옮긴다. 시간은 흐르지 않는다
         *     일러스트를 여는 것은 효과가 아니라 장면의 칸(collectible)이다. 이벤트가 열리면 그 장면의 일러스트를 연다.
         * @enum {string}
         */
        EffectKind: "affection" | "give_item" | "take_item" | "accompany_start" | "accompany_end" | "move_to";
        /**
         * Ending
         * @description 엔딩 하나(story.md 의 "고백과 엔딩"). trigger 가 일어나면 그 시작의 엔딩을 적은 차례로 맞춰 보고 when 이 맞는
         *     첫 엔딩을 고른다. scene 은 엔딩의 장면이다(모델이 쓴다). unlock 이면 계정의 엔딩 기록과 갤러리에 남는다.
         *     hint 는 못 본 사람에게 보이는 한 줄이다. 못 본 엔딩의 이름은 story 가 내려보내지 않는다.
         */
        Ending: {
            /**
             * Hint
             * @default
             */
            hint: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            scene: components["schemas"]["Scene"];
            trigger: components["schemas"]["app__worlds__schemas__Trigger"];
            /**
             * Unlock
             * @default true
             */
            unlock: boolean;
            /**
             * @default {
             *       "items": [],
             *       "match": "all"
             *     }
             */
            when: components["schemas"]["Conditions"];
        };
        /**
         * EndingDocument
         * @description 엔딩 하나. 판의 차례가 맞춰 보는 차례다.
         */
        EndingDocument: {
            /** Hint */
            hint: string;
            /** Id */
            id: string;
            /** Name */
            name: string;
            scene: components["schemas"]["SceneDocument"];
            trigger: components["schemas"]["app__worlds__documents__TriggerDocument"];
            /** Unlock */
            unlock: boolean;
            when: components["schemas"]["ConditionsDocument"];
        };
        /**
         * EndingTrigger
         * @description 엔딩의 판정이 무엇으로 시작되는가(story.md 의 "고백과 엔딩").
         *     그 인물에게 고백 성공(confess_success, target: 인물), 실패(confess_fail, target: 인물),
         *     기한이 지났다(deadline, target 없음), 그 이벤트가 열렸다(event, target: 이벤트).
         *     시작이 일어나면 그 시작의 엔딩을 적은 차례로 맞춰 보고 처음 맞는 것 하나를 고른다.
         * @enum {string}
         */
        EndingTrigger: "confess_success" | "confess_fail" | "deadline" | "event";
        /**
         * Event
         * @description 이벤트 하나(story.md 의 "이벤트"). 행동 뒤에 엔진이 when 을 맞춰 보고, 맞는 것 가운데 적은 차례로 하나만 연다.
         *     열리면 on_open 의 효과를 반영하고, 이어지는 응답이 scene 을 받아 그 장면을 쓴다.
         *     choices 가 있으면 화면이 응답 밑에 보이고, 고르면 그 효과를 반영한 뒤 모델이 반응을 쓴다.
         *     repeat 이 아니면 한 번만 열린다. id 는 세계관 안에서 고유하고, 조건(event_seen)과 story 의 "본 이벤트"가 적는다.
         */
        Event: {
            /**
             * Choices
             * @default []
             */
            choices: components["schemas"]["Choice"][];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /**
             * On Open
             * @default []
             */
            on_open: components["schemas"]["Effect"][];
            /**
             * Repeat
             * @default false
             */
            repeat: boolean;
            scene: components["schemas"]["Scene"];
            /**
             * @default {
             *       "items": [],
             *       "match": "all"
             *     }
             */
            when: components["schemas"]["Conditions"];
        };
        /**
         * EventDocument
         * @description 이벤트 하나. 판의 차례가 여는 차례다.
         */
        EventDocument: {
            /** Choices */
            choices: components["schemas"]["ChoiceDocument"][];
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** On Open */
            on_open: components["schemas"]["EffectDocument"][];
            /** Repeat */
            repeat: boolean;
            scene: components["schemas"]["SceneDocument"];
            when: components["schemas"]["ConditionsDocument"];
        };
        /**
         * EventScene
         * @description 이벤트 씬 하나(#669). 조건이 맞은 뒤의 첫 응답에 붙어 배경과 캐릭터를 대신한다(chat).
         *     collectible 이면 해금 대상이다. 한 번 열면 계정에 남고 갤러리와 소개의 칸에 보인다.
         *     아니면 이야기 중에만 나온다(칸도 보이지 않는다). description 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다.
         */
        EventScene: {
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
            when: components["schemas"]["SceneCondition"];
        };
        /**
         * EventSceneDocument
         * @description 이벤트 씬 하나. collectible 이면 해금 대상이다. description 은 그 답을 쓸 때 모델이 읽는 장면의 설명이다.
         */
        EventSceneDocument: {
            /** Collectible */
            collectible: boolean;
            /** Description */
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
         * Gift
         * @description 선물의 규칙 하나. 그 물건을 건네면 호감도를 change 만큼 바꾼다(0~100 안으로 자른다).
         *     once 면 그 가지에서 처음 한 번만이다. id 는 인물 안에서 고유하고, story 가 "이미 했다"를 적는다.
         */
        Gift: {
            /** Change */
            change: number;
            /** Id */
            id: string;
            /** Item */
            item: string;
            /**
             * Once
             * @default false
             */
            once: boolean;
        };
        /**
         * GiftDocument
         * @description 선물의 규칙 하나.
         */
        GiftDocument: {
            /** Change */
            change: number;
            /** Id */
            id: string;
            /** Item */
            item: string;
            /** Once */
            once: boolean;
        };
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /**
         * HiddenInput
         * @description 숨기기(true)와 풀기(false). reason 은 감사 기록의 사유다.
         */
        HiddenInput: {
            /** Hidden */
            hidden: boolean;
            /** Reason */
            reason: string;
        };
        /**
         * HiddenResult
         * @description 조치한 뒤 캐릭터(또는 세계관)가 숨겨져 있는가.
         */
        HiddenResult: {
            /** Hidden */
            hidden: boolean;
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
            /**
             * Giftable
             * @default false
             */
            giftable: boolean;
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
            /**
             * Giftable
             * @default false
             */
            giftable: boolean;
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
         * LoreEntry
         * @description 항목 하나. 이름과 내용은 모델에 간다. constant 면 늘 간다.
         */
        LoreEntry: {
            /**
             * Constant
             * @default false
             */
            constant: boolean;
            /** Content */
            content: string;
            /** Id */
            id: string;
            /**
             * Keywords
             * @default []
             */
            keywords: string[];
            /** @default other */
            kind: components["schemas"]["LoreKind"];
            /** Name */
            name: string;
        };
        /**
         * LoreEntryDocument
         * @description 항목 하나. constant 면 늘 모델에 간다. 아니면 최근 대화에 키워드가 나올 때 간다(고르는 것은 chat 이다).
         */
        LoreEntryDocument: {
            /** Constant */
            constant: boolean;
            /** Content */
            content: string;
            /** Id */
            id: string;
            /** Keywords */
            keywords: string[];
            kind: components["schemas"]["LoreKind"];
            /** Name */
            name: string;
        };
        /**
         * LoreKind
         * @description 로어북 항목의 종류. TRPG 의 LoreKind 와 같은 값이다. chat 은 지금 종류로 다르게 다루지 않는다(보이기만 한다).
         *     인물, 장소, 물건, 세력, 종족, 전설(사실인지 애매한 이야기), 사건, 기타.
         * @enum {string}
         */
        LoreKind: "person" | "place" | "item" | "faction" | "species" | "legend" | "event" | "other";
        /**
         * LorebookCopyDocument
         * @description 캐릭터의 판에 복사한 로어북 하나(#672). id 와 version 은 로어북과 그 판의 번호다(어디서 왔는지 적어 둔다).
         */
        LorebookCopyDocument: {
            /** Entries */
            entries: components["schemas"]["LoreEntryDocument"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Version */
            version: number;
        };
        /**
         * LorebookCreate
         * @description 로어북을 만들 때 받는 값. 이름만 필수다.
         */
        LorebookCreate: {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Entries
             * @default []
             */
            entries: components["schemas"]["LoreEntry"][];
            /** Name */
            name: string;
        };
        /**
         * LorebookDetail
         * @description 로어북의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null).
         */
        LorebookDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** Entries */
            entries: components["schemas"]["LoreEntry"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latest Version */
            latest_version: number | null;
            /** Name */
            name: string;
            /** Published At */
            published_at: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * LorebookDocument
         * @description 판에 굳힌 로어북. 설명은 만든 사람이 보는 것이라 판에 넣지 않는다.
         */
        LorebookDocument: {
            /** Entries */
            entries: components["schemas"]["LoreEntryDocument"][];
            /** Format */
            format: number;
            /** Name */
            name: string;
        };
        /**
         * LorebookPage
         * @description 목록의 한 쪽과 전체 개수.
         */
        LorebookPage: {
            /** Items */
            items: components["schemas"]["LorebookSummary"][];
            /** Total */
            total: number;
        };
        /**
         * LorebookSummary
         * @description 내 로어북 목록의 한 줄. entry_count 는 초안의 항목 수다.
         */
        LorebookSummary: {
            /** Entry Count */
            entry_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latest Version */
            latest_version: number | null;
            /** Name */
            name: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * LorebookUpdate
         * @description 로어북을 고칠 때 받는 값. 보낸 칸만 바꾼다. 게시한 판은 그대로다. null 은 받지 않는다.
         */
        LorebookUpdate: {
            /** Description */
            description?: string | null;
            /** Entries */
            entries?: components["schemas"]["LoreEntry"][] | null;
            /** Name */
            name?: string | null;
        };
        /**
         * LorebookVersionCreate
         * @description 게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다).
         */
        LorebookVersionCreate: {
            /**
             * Note
             * @default
             */
            note: string;
        };
        /**
         * LorebookVersionDetail
         * @description 판 하나. 굳힌 문서까지 싣는다.
         */
        LorebookVersionDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            document: components["schemas"]["LorebookDocument"];
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
         * LorebookVersionSummary
         * @description 판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다.
         */
        LorebookVersionSummary: {
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
         * MapPresence
         * @description 지도에 인물이 있는 곳을 보이는가. 보임, 숨김, 호감도가 정한 단계 이상일 때만(stage).
         * @enum {string}
         */
        MapPresence: "shown" | "hidden" | "stage";
        /**
         * Match
         * @description 조건 목록을 맞추는 법. 모두, 또는 하나라도(TRPG 의 퀘스트와 같다).
         * @enum {string}
         */
        Match: "all" | "any";
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
         * OpenReportGroupOut
         * @description 열린 신고를 캐릭터마다 묶은 한 줄. reasons 는 사유마다의 수다. hidden 은 이미 숨긴 캐릭터인가.
         */
        OpenReportGroupOut: {
            /**
             * Character Id
             * Format: uuid
             */
            character_id: string;
            /**
             * First Reported At
             * Format: date-time
             */
            first_reported_at: string;
            /** Hidden */
            hidden: boolean;
            /**
             * Last Reported At
             * Format: date-time
             */
            last_reported_at: string;
            /** Name */
            name: string;
            /** Open Count */
            open_count: number;
            /** Reasons */
            reasons: {
                [key: string]: number;
            };
        };
        /**
         * OpenReportPage
         * @description 열린 신고의 묶음 한 쪽과 전체 묶음의 수.
         */
        OpenReportPage: {
            /** Items */
            items: components["schemas"]["OpenReportGroupOut"][];
            /** Total */
            total: number;
        };
        /**
         * OutcomeInput
         * @description 열린 신고의 처리. actioned 면 캐릭터를 숨긴다. reason 은 감사 기록의 사유다.
         */
        OutcomeInput: {
            outcome: components["schemas"]["ReportOutcome"];
            /** Reason */
            reason: string;
        };
        /**
         * OutcomeResult
         * @description 처리한 신고의 수와, 처리한 뒤 캐릭터가 숨겨져 있는가.
         */
        OutcomeResult: {
            /** Handled */
            handled: number;
            /** Hidden */
            hidden: boolean;
        };
        /**
         * PanelField
         * @description 인물 창에 보이는 항목. 소개, 나이, 성별, 호감도.
         * @enum {string}
         */
        PanelField: "intro" | "age" | "gender" | "affection";
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
         * PublicCastMember
         * @description 소개에 보이는 인물 하나. reveal 이 silhouette 이면 이름과 그림을 싣지 않는다(null).
         *     숨김(hidden)인 인물은 목록에 없다.
         */
        PublicCastMember: {
            /** Id */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Name */
            name: string | null;
            reveal: components["schemas"]["Reveal"];
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
         * PublicWorldDetail
         * @description 공개 세계관의 소개(D1). 마지막 판에서 보여도 되는 것만 골라 싣는다.
         *     이벤트, 조건, 엔딩의 이름과 조건, 인물의 일정과 호감도 규칙은 싣지 않는다(플레이의 내용이다).
         *     intro_html 은 게시할 때 거른 소개다. ending_count 는 계정에 남는 엔딩(unlock)의 수다.
         */
        PublicWorldDetail: {
            after_ending: components["schemas"]["AfterEnding"];
            /** Cast */
            cast: components["schemas"]["PublicCastMember"][];
            /** Deadline Days */
            deadline_days: number | null;
            /** Ending Count */
            ending_count: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
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
         * PublicWorldPage
         * @description 공개 목록의 한 쪽과 전체 개수.
         */
        PublicWorldPage: {
            /** Items */
            items: components["schemas"]["PublicWorldSummary"][];
            /** Total */
            total: number;
        };
        /**
         * PublicWorldSummary
         * @description 공개 목록의 한 줄. 마지막 판의 값이다. deadline_days 는 기한(날 수)이고 없으면 null 이다.
         */
        PublicWorldSummary: {
            /** Deadline Days */
            deadline_days: number | null;
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
         * ReportCreate
         * @description 신고할 때 받는 값. 사유가 other 면 설명이 있어야 한다(게시판의 신고와 같다).
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
         * @description 접수한 신고. 화면이 "접수했습니다"를 보인다.
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
         * ReportOut
         * @description 신고 하나(운영자가 본다). 신고한 사람의 id 는 싣지 않는다. 처리하는 데 필요하지 않다.
         */
        ReportOut: {
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
            outcome: components["schemas"]["ReportOutcome"] | null;
            reason: components["schemas"]["ReportReason"];
            /** Version */
            version: number;
        };
        /**
         * ReportOutcome
         * @description 처리의 결과. 받아들였다(캐릭터를 숨겼다), 받아들이지 않았다.
         * @enum {string}
         */
        ReportOutcome: "actioned" | "dismissed";
        /**
         * ReportReason
         * @description 신고의 사유. 게시판의 다섯에 minor(미성년 인물을 성적으로 다룬다)를 더했다(2026-10-23 유저 결정).
         *     minor 는 약관이 금지하는 선이라 운영자의 목록에서 가장 먼저 보인다.
         * @enum {string}
         */
        ReportReason: "spam" | "abuse" | "sexual" | "minor" | "illegal" | "other";
        /**
         * Reveal
         * @description 인물을 사람에게 어떻게 보이는가. 보임, 실루엣(이름과 그림을 가린다), 숨김(목록에 없다).
         * @enum {string}
         */
        Reveal: "shown" | "silhouette" | "hidden";
        /**
         * Scene
         * @description 이벤트의 장면 지시. text 는 모델에게 주는 상황 설명이다. cast 는 장면에 불러들이는 인물(4명까지)이다.
         *     image_id 는 일러스트다. 있으면 그림 창의 배경과 캐릭터를 대신한다. collectible 이면 열릴 때 계정에 남는다(갤러리).
         */
        Scene: {
            /**
             * Cast
             * @default []
             */
            cast: string[];
            /**
             * Collectible
             * @default false
             */
            collectible: boolean;
            /** Image Id */
            image_id?: string | null;
            /** Text */
            text: string;
        };
        /**
         * SceneCondition
         * @description 이벤트 씬이 나오는 조건. target 은 장소나 물건의 id, 또는 호감도 단계의 이름이다.
         */
        SceneCondition: {
            kind: components["schemas"]["SceneWhen"];
            /** Target */
            target: string;
        };
        /**
         * SceneConditionDocument
         * @description 이벤트 씬이 나오는 조건(종류, 대상).
         */
        SceneConditionDocument: {
            kind: components["schemas"]["SceneWhen"];
            /** Target */
            target: string;
        };
        /**
         * SceneDocument
         * @description 이벤트의 장면 지시.
         */
        SceneDocument: {
            /** Cast */
            cast: string[];
            /** Collectible */
            collectible: boolean;
            /** Image Id */
            image_id: string | null;
            /** Text */
            text: string;
        };
        /**
         * SceneWhen
         * @description 이벤트 씬이 나오는 조건의 종류(#669). 호감도의 규칙과 같은 (종류, 대상) 모양이다.
         *     그 장소에 갔다(reach_place, 장소의 id), 그 물건을 처음 건넸다(give_item, 물건의 id),
         *     호감도가 그 단계에 이르렀다(affection_stage, 단계의 이름). 맞추는 것은 chat 의 엔진이다.
         * @enum {string}
         */
        SceneWhen: "reach_place" | "give_item" | "affection_stage";
        /**
         * ScheduleLine
         * @description 일정의 줄 하나(story.md 의 "인물과 장면"). 그 시간대에 조건이 맞으면 그 장소에 있다.
         *     위에 적은 줄부터 맞춰 본다. 맞는 줄이 없으면 기본 장소(home)다.
         */
        ScheduleLine: {
            /** Place */
            place: string;
            /** Slot */
            slot: string;
            /**
             * @default {
             *       "items": [],
             *       "match": "all"
             *     }
             */
            when: components["schemas"]["Conditions"];
        };
        /**
         * ScheduleLineDocument
         * @description 일정의 줄 하나. 위의 줄부터 맞춰 본다.
         */
        ScheduleLineDocument: {
            /** Place */
            place: string;
            /** Slot */
            slot: string;
            when: components["schemas"]["ConditionsDocument"];
        };
        /**
         * Show
         * @description 보이기의 기본. 인물의 공개, 지도에 인물을 보이는지, 인물 창의 항목이다. 인물마다 덮어쓴다.
         */
        Show: {
            /** @default shown */
            map: components["schemas"]["MapPresence"];
            /**
             * Panel
             * @default [
             *       "intro",
             *       "age",
             *       "gender",
             *       "affection"
             *     ]
             */
            panel: components["schemas"]["PanelField"][];
            /** @default shown */
            reveal: components["schemas"]["Reveal"];
        };
        /**
         * Slot
         * @description 시간대 하나. start_hour 는 이 시간대가 시작하는 시각(몇 시)이다. 다음 시간대가 시작할 때까지 이 시간대다.
         *     마지막 시간대는 자정을 넘어 첫 시간대가 시작할 때까지다(story.md 의 "시각").
         */
        Slot: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Start Hour */
            start_hour: number;
        };
        /**
         * SlotDocument
         * @description 시간대 하나. start_hour 부터 다음 시간대가 시작할 때까지다.
         */
        SlotDocument: {
            /** Id */
            id: string;
            /** Name */
            name: string;
            /** Start Hour */
            start_hour: number;
        };
        /**
         * Sprite
         * @description 캐릭터 그림 하나. 배경이 투명한 서 있는 그림이고, 대화의 그림 창에서 배경 위에 겹친다.
         *     expression 은 표정의 이름이다(빈 글이면 기본 표정). outfit 은 이 그림의 차림인 옷(물건의 id)이다.
         *     비어 있으면 처음 차림이다. 사용자가 그 옷을 건네 상대가 입으면 그 차림의 그림을 쓴다(chat).
         *     투명한지는 서버가 보지 않는다(2026-10-23 유저 결정). 만드는 화면이 미리 보기로 보인다.
         */
        Sprite: {
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
         * SpriteDocument
         * @description 캐릭터 그림 하나. expression 은 표정(빈 글이면 기본), outfit 은 차림인 옷(물건의 id, 없으면 처음 차림)이다.
         */
        SpriteDocument: {
            /** Expression */
            expression: string;
            /** Id */
            id: string;
            /**
             * Image Id
             * Format: uuid
             */
            image_id: string;
            /** Outfit */
            outfit: string | null;
        };
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
         * TimeOfDay
         * @description 하루의 어느 때. 장소의 시간대 배경을 고르는 열쇠다.
         *     경계는 TRPG 와 같다(trpg-server 의 app/calendar/clock.py, 2026-10-22 유저 결정). 계산은 chat 이 한다.
         * @enum {string}
         */
        TimeOfDay: "dawn" | "morning" | "day" | "evening" | "night";
        /**
         * TriggerKind
         * @description 호감도를 바꾸는 사용자의 행동. TRPG 의 퀘스트 조건과 같은 (종류, 대상) 모양이다.
         *     물건을 건넸다(give_item), 장소에 갔다(reach_place), 물건을 썼다(use_item).
         * @enum {string}
         */
        TriggerKind: "give_item" | "reach_place" | "use_item";
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
        /**
         * WorldCopy
         * @description story 서버에 내주는 판. 세션을 시작할 때 가져가 고정한다.
         *     가져간 쪽은 번호를 적어 두고, 지금의 번호(WorldVersionNumber)가 크면 "새 판이 있다"를 알린다.
         */
        WorldCopy: {
            document: components["schemas"]["WorldDocument"];
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
         * WorldCreate
         * @description 세계관을 만들 때 받는 값. 이름만 필수다. 시간대는 아침, 낮, 저녁, 밤에서 시작한다. 처음에는 비공개다.
         */
        WorldCreate: {
            /** @default end */
            after_ending: components["schemas"]["AfterEnding"];
            /**
             * Cast
             * @default []
             */
            cast: components["schemas"]["CastMember"][];
            /** Deadline Days */
            deadline_days?: number | null;
            /**
             * Endings
             * @default []
             */
            endings: components["schemas"]["Ending"][];
            /**
             * Events
             * @default []
             */
            events: components["schemas"]["Event"][];
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
            items: components["schemas"]["WorldItem"][];
            /**
             * Lorebooks
             * @default []
             */
            lorebooks: string[];
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
            places: components["schemas"]["WorldPlace"][];
            /** @default all */
            rating: components["schemas"]["Rating"];
            /**
             * @default {
             *       "map": "shown",
             *       "panel": [
             *         "intro",
             *         "age",
             *         "gender",
             *         "affection"
             *       ],
             *       "reveal": "shown"
             *     }
             */
            show: components["schemas"]["Show"];
            /**
             * Slots
             * @default [
             *       {
             *         "id": "morning",
             *         "name": "아침",
             *         "start_hour": 7
             *       },
             *       {
             *         "id": "day",
             *         "name": "낮",
             *         "start_hour": 11
             *       },
             *       {
             *         "id": "evening",
             *         "name": "저녁",
             *         "start_hour": 17
             *       },
             *       {
             *         "id": "night",
             *         "name": "밤",
             *         "start_hour": 21
             *       }
             *     ]
             */
            slots: components["schemas"]["Slot"][];
            /**
             * Start Items
             * @default []
             */
            start_items: components["schemas"]["StartItem"][];
            /** Start Place */
            start_place?: string | null;
            /** Start Slot */
            start_slot?: string | null;
            /**
             * Tags
             * @default []
             */
            tags: string[];
        };
        /**
         * WorldDetail
         * @description 세계관의 초안 하나. 만든 사람만 본다. latest_version 은 마지막으로 게시한 판의 번호다(없으면 null).
         */
        WorldDetail: {
            after_ending: components["schemas"]["AfterEnding"];
            /** Cast */
            cast: components["schemas"]["CastMember"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Deadline Days */
            deadline_days: number | null;
            /** Endings */
            endings: components["schemas"]["Ending"][];
            /** Events */
            events: components["schemas"]["Event"][];
            /** Hidden At */
            hidden_at?: string | null;
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
            items: components["schemas"]["WorldItem"][];
            /** Latest Version */
            latest_version: number | null;
            /** Lorebooks */
            lorebooks: string[];
            /** Name */
            name: string;
            /** Paths */
            paths: components["schemas"]["Path"][];
            /** Places */
            places: components["schemas"]["WorldPlace"][];
            /** Published At */
            published_at: string | null;
            rating: components["schemas"]["Rating"];
            show: components["schemas"]["Show"];
            /** Slots */
            slots: components["schemas"]["Slot"][];
            /** Start Items */
            start_items: components["schemas"]["StartItem"][];
            /** Start Place */
            start_place: string | null;
            /** Start Slot */
            start_slot: string | null;
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
         * WorldDocument
         * @description 판에 굳힌 세계관. intro_html 은 허용 목록으로 거른 소개다.
         */
        WorldDocument: {
            after_ending: components["schemas"]["AfterEnding"];
            /** Cast */
            cast: components["schemas"]["CastDocument"][];
            /** Deadline Days */
            deadline_days: number | null;
            /**
             * Endings
             * @default []
             */
            endings: components["schemas"]["EndingDocument"][];
            /**
             * Events
             * @default []
             */
            events: components["schemas"]["EventDocument"][];
            /** Format */
            format: number;
            /** Image Id */
            image_id: string | null;
            /** Intro Html */
            intro_html: string;
            /** Items */
            items: components["schemas"]["WorldItemDocument"][];
            /** Lorebooks */
            lorebooks: components["schemas"]["LorebookCopyDocument"][];
            /** Name */
            name: string;
            /** Paths */
            paths: components["schemas"]["PathDocument"][];
            /** Places */
            places: components["schemas"]["WorldPlaceDocument"][];
            rating: components["schemas"]["Rating"];
            /** Slots */
            slots: components["schemas"]["SlotDocument"][];
            /** Start Items */
            start_items: components["schemas"]["app__worlds__documents__StartItemDocument"][];
            /** Start Place */
            start_place: string;
            /** Start Slot */
            start_slot: string;
            /** Tags */
            tags: string[];
        };
        /**
         * WorldItem
         * @description 물건 하나. consumable 이면 쓰면 하나 없어진다. 건네는 것과 호감도는 인물의 선물 규칙이 정한다.
         */
        WorldItem: {
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
            /** Name */
            name: string;
        };
        /**
         * WorldItemDocument
         * @description 물건 하나.
         */
        WorldItemDocument: {
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
         * WorldPage
         * @description 목록의 한 쪽과 전체 개수.
         */
        WorldPage: {
            /** Items */
            items: components["schemas"]["WorldSummary"][];
            /** Total */
            total: number;
        };
        /**
         * WorldPlace
         * @description 장소 하나. 캐릭터의 장소와 같고, 시간대마다의 배경(backgrounds)의 열쇠가 그 세계관의 시간대 id 다.
         *     그 시간대의 배경이 없으면 기본 배경(image_id)을 쓴다.
         */
        WorldPlace: {
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
         * WorldPlaceDocument
         * @description 장소 하나. backgrounds 의 열쇠는 시간대의 id 다.
         */
        WorldPlaceDocument: {
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
         * WorldPublishCheck
         * @description 지금 게시하면 막히는 이유, 알리는 것, 걸러질 것. 판을 만들지 않는다.
         *
         *     problems 는 게시가 409 로 돌려주는 것과 같은 이름이다. 비어 있으면 게시할 수 있다(ready).
         *     warnings 는 막지 않는다(닿지 않는 장소 등, 2026-10-24 유저 결정).
         */
        WorldPublishCheck: {
            /** Problems */
            problems: string[];
            /** Ready */
            ready: boolean;
            /** Removed */
            removed: components["schemas"]["RemovedItem"][];
            /** Warnings */
            warnings: string[];
        };
        /**
         * WorldPublishResult
         * @description 게시한 결과. 새 판과, 소개에서 걸러 낸 것들(removed), 알리는 것들(warnings)이다.
         *
         *     걸러 낸 것과 알리는 것이 있어도 게시는 된다. 화면이 제작자에게 보인다.
         */
        WorldPublishResult: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            document: components["schemas"]["WorldDocument"];
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
            /** Warnings */
            warnings: string[];
        };
        /**
         * WorldSummary
         * @description 내 세계관 목록의 한 줄.
         */
        WorldSummary: {
            /** Hidden At */
            hidden_at?: string | null;
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
         * WorldUpdate
         * @description 세계관을 고칠 때 받는 값. 보낸 칸만 바꾼다. 초안만 바뀐다. 게시한 판은 그대로다.
         *
         *     null 은 그림, 시작 장소와 시간대, 기한만 받는다. 공개 범위(visibility)도 여기서 바꾼다(공개는 운영자만, 1~2단계).
         */
        WorldUpdate: {
            after_ending?: components["schemas"]["AfterEnding"] | null;
            /** Cast */
            cast?: components["schemas"]["CastMember"][] | null;
            /** Deadline Days */
            deadline_days?: number | null;
            /** Endings */
            endings?: components["schemas"]["Ending"][] | null;
            /** Events */
            events?: components["schemas"]["Event"][] | null;
            /** Image Id */
            image_id?: string | null;
            /** Intro Html */
            intro_html?: string | null;
            /** Items */
            items?: components["schemas"]["WorldItem"][] | null;
            /** Lorebooks */
            lorebooks?: string[] | null;
            /** Name */
            name?: string | null;
            /** Paths */
            paths?: components["schemas"]["Path"][] | null;
            /** Places */
            places?: components["schemas"]["WorldPlace"][] | null;
            rating?: components["schemas"]["Rating"] | null;
            show?: components["schemas"]["Show"] | null;
            /** Slots */
            slots?: components["schemas"]["Slot"][] | null;
            /** Start Items */
            start_items?: components["schemas"]["StartItem"][] | null;
            /** Start Place */
            start_place?: string | null;
            /** Start Slot */
            start_slot?: string | null;
            /** Tags */
            tags?: string[] | null;
            visibility?: components["schemas"]["Visibility"] | null;
        };
        /**
         * WorldVersionCreate
         * @description 게시할 때 받는 값. 이번 판에서 무엇이 바뀌었는지 적는다(비워도 된다).
         */
        WorldVersionCreate: {
            /**
             * Note
             * @default
             */
            note: string;
        };
        /**
         * WorldVersionDetail
         * @description 판 하나. 굳힌 문서까지 싣는다.
         */
        WorldVersionDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            document: components["schemas"]["WorldDocument"];
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
         * WorldVersionNumber
         * @description 세계관의 지금 판 번호. 화면을 열 때 한 번 묻는다. 문서는 싣지 않는다.
         */
        WorldVersionNumber: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Version */
            version: number;
        };
        /**
         * WorldVersionSummary
         * @description 판의 목록에 싣는 값. 굳힌 문서는 싣지 않는다.
         */
        WorldVersionSummary: {
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
         * StartItemDocument
         * @description 사용자가 처음에 가진 물건(item 은 물건의 id)과 그 수.
         */
        app__characters__documents__StartItemDocument: {
            /** Count */
            count: number;
            /** Item */
            item: string;
        };
        /**
         * TriggerDocument
         * @description 호감도를 바꾸는 행동(종류, 대상).
         */
        app__characters__documents__TriggerDocument: {
            kind: components["schemas"]["TriggerKind"];
            /** Target */
            target: string;
        };
        /**
         * Trigger
         * @description 호감도를 바꾸는 사용자의 행동. target 은 그 물건이나 장소의 id 다.
         */
        app__characters__schemas__Trigger: {
            kind: components["schemas"]["TriggerKind"];
            /** Target */
            target: string;
        };
        /**
         * StartItemDocument
         * @description 사용자가 처음에 가진 물건과 그 수.
         */
        app__worlds__documents__StartItemDocument: {
            /** Count */
            count: number;
            /** Item */
            item: string;
        };
        /**
         * TriggerDocument
         * @description 엔딩의 시작. 기한은 target 이 없다.
         */
        app__worlds__documents__TriggerDocument: {
            kind: components["schemas"]["EndingTrigger"];
            /** Target */
            target: string | null;
        };
        /**
         * Trigger
         * @description 엔딩의 시작. 고백 성공과 실패는 인물, 이벤트는 이벤트의 id 를 target 에 적는다. 기한은 target 이 없다.
         */
        app__worlds__schemas__Trigger: {
            kind: components["schemas"]["EndingTrigger"];
            /** Target */
            target?: string | null;
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
    list_open_reports_api_v1_asset_admin_character_reports_get: {
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
                    "application/json": components["schemas"]["OpenReportPage"];
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
    change_hidden_api_v1_asset_admin_characters__character_id__hidden_put: {
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
                "application/json": components["schemas"]["HiddenInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HiddenResult"];
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
    list_character_reports_api_v1_asset_admin_characters__character_id__reports_get: {
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
                    "application/json": components["schemas"]["ReportOut"][];
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
    handle_reports_api_v1_asset_admin_characters__character_id__reports_outcome_put: {
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
                "application/json": components["schemas"]["OutcomeInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutcomeResult"];
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
    change_world_hidden_api_v1_asset_admin_worlds__world_id__hidden_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HiddenInput"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HiddenResult"];
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
    report_character_api_v1_asset_listings_characters__character_id__reports_post: {
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
    list_public_api_v1_asset_listings_worlds_get: {
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
                    "application/json": components["schemas"]["PublicWorldPage"];
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
    read_public_api_v1_asset_listings_worlds__world_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["PublicWorldDetail"];
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
    list_lorebooks_api_v1_asset_lorebooks_get: {
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
                    "application/json": components["schemas"]["LorebookPage"];
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
    create_lorebook_api_v1_asset_lorebooks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LorebookCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LorebookDetail"];
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
    read_lorebook_api_v1_asset_lorebooks__lorebook_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
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
                    "application/json": components["schemas"]["LorebookDetail"];
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
    delete_lorebook_api_v1_asset_lorebooks__lorebook_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
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
    update_lorebook_api_v1_asset_lorebooks__lorebook_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LorebookUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LorebookDetail"];
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
    list_versions_api_v1_asset_lorebooks__lorebook_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
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
                    "application/json": components["schemas"]["LorebookVersionSummary"][];
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
    publish_api_v1_asset_lorebooks__lorebook_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LorebookVersionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LorebookVersionDetail"];
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
    read_version_api_v1_asset_lorebooks__lorebook_id__versions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
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
                    "application/json": components["schemas"]["LorebookVersionDetail"];
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
    copy_latest_api_v1_asset_service__caller__worlds__world_id__latest_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldCopy"];
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
    read_latest_number_api_v1_asset_service__caller__worlds__world_id__latest_number_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldVersionNumber"];
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
    list_worlds_api_v1_asset_worlds_get: {
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
                    "application/json": components["schemas"]["WorldPage"];
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
    create_world_api_v1_asset_worlds_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorldCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorldDetail"];
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
    read_world_api_v1_asset_worlds__world_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldDetail"];
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
    delete_world_api_v1_asset_worlds__world_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
    update_world_api_v1_asset_worlds__world_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorldUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorldDetail"];
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
    check_publish_api_v1_asset_worlds__world_id__publish_check_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldPublishCheck"];
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
    list_versions_api_v1_asset_worlds__world_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldVersionSummary"][];
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
    publish_api_v1_asset_worlds__world_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WorldVersionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorldPublishResult"];
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
    read_version_api_v1_asset_worlds__world_id__versions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                world_id: string;
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
                    "application/json": components["schemas"]["WorldVersionDetail"];
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
