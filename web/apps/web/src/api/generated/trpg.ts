// web/apps/web/src/api/generated/trpg.ts
// docs/api/trpg.openapi.json 에서 만든 타입. 손으로 고치지 않는다(npm run gen:api).

export interface paths {
    "/api/v1/game/admin/scenarios/{scenario_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Scenario
         * @description 남의 시나리오의 초안을 만든 사람이 보는 모양 그대로 본다.
         */
        get: operations["read_scenario_api_v1_game_admin_scenarios__scenario_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/scenarios/{scenario_id}/sanction": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Sanction Scenario
         * @description 공개 중인 판을 제재한다. 공개를 내리고 그 판을 다시 공개하지 못하게 한다. 제작자는 혼자서는 계속 쓴다.
         *
         *     공개 중인 판이 없으면 409(not_published). 제작자의 제재가 정해진 수에 닿으면 저절로 공개 금지가 된다.
         */
        post: operations["sanction_scenario_api_v1_game_admin_scenarios__scenario_id__sanction_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/scenarios/{scenario_id}/versions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Version
         * @description 남의 시나리오의 판 하나를 굳힌 내용 전부와 함께 본다. 테이블은 이 내용으로 돈다.
         */
        get: operations["read_version_api_v1_game_admin_scenarios__scenario_id__versions__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/tables/{table_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Table
         * @description 테이블 하나를 굳힌 판의 내용 전부와 함께 본다. 앉아 있지 않아도 된다.
         */
        get: operations["read_table_api_v1_game_admin_tables__table_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/tables/{table_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * End Table
         * @description 테이블을 끝낸다. 앉은 사람에게는 "운영자가 끝냈다"가 보인다. 이미 끝났으면 409(already_ended).
         */
        post: operations["end_table_api_v1_game_admin_tables__table_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/tables/{table_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Events
         * @description 테이블의 기록(서술, 행동, 판정)을 일어난 순서대로 본다. 넘기는 법은 앉은 사람의 것과 같다(after).
         */
        get: operations["read_events_api_v1_game_admin_tables__table_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/tables/{table_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Messages
         * @description 테이블 대화를 쓴 순서대로 본다.
         */
        get: operations["read_messages_api_v1_game_admin_tables__table_id__messages_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/tables/{table_id}/whispers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Whispers
         * @description 테이블의 귓속말 전부를 보낸 순서대로 본다. 누가 누구에게 보냈는지, GM 에게 보였는지가 함께 온다.
         */
        get: operations["read_whispers_api_v1_game_admin_tables__table_id__whispers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/users/{user_id}/publishing-ban": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Ban Publisher
         * @description 한 사람의 공개를 금지한다. 이미 금지 중이면 409(already_banned). 플레이는 막지 않는다.
         */
        post: operations["ban_publisher_api_v1_game_admin_users__user_id__publishing_ban_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/admin/users/{user_id}/publishing-ban/lift": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Lift Ban
         * @description 공개 금지를 푼다. 금지 중이 아니면 409(not_banned). 그 뒤의 제재부터 다시 센다.
         */
        post: operations["lift_ban_api_v1_game_admin_users__user_id__publishing_ban_lift_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/bestiaries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Bestiaries
         * @description 자기 도감의 목록을 최근에 만든 것부터 돌려준다.
         */
        get: operations["list_bestiaries_api_v1_game_bestiaries_get"];
        put?: never;
        /**
         * Create Bestiary
         * @description 도감을 만든다. 몬스터는 만든 뒤에 하나씩 더한다.
         */
        post: operations["create_bestiary_api_v1_game_bestiaries_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/bestiaries/{bestiary_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Bestiary
         * @description 자기 도감 하나를 돌려준다. 몬스터는 싣지 않는다. 몬스터는 몬스터의 주소에서 읽는다.
         */
        get: operations["read_bestiary_api_v1_game_bestiaries__bestiary_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Bestiary
         * @description 자기 도감을 지운다.
         */
        delete: operations["delete_bestiary_api_v1_game_bestiaries__bestiary_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Bestiary
         * @description 자기 도감을 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_bestiary_api_v1_game_bestiaries__bestiary_id__patch"];
        trace?: never;
    };
    "/api/v1/game/bestiaries/{bestiary_id}/monsters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Monsters
         * @description 자기 도감의 몬스터를 만든 순서대로 전부 돌려준다.
         */
        get: operations["list_monsters_api_v1_game_bestiaries__bestiary_id__monsters_get"];
        put?: never;
        /**
         * Add Monster
         * @description 자기 도감에 몬스터를 더한다.
         */
        post: operations["add_monster_api_v1_game_bestiaries__bestiary_id__monsters_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/bestiaries/{bestiary_id}/monsters/copies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Copy To Bestiary
         * @description 고른 참고 자료(몬스터)를 자기 도감의 몬스터로 복사한다. 원본의 생물 분류를 도감의 타입으로 바꾼다.
         *
         *     몬스터가 아닌 줄이 있으면 422(not_a_monster)다. 건너뛰기와 상한은 로어북과 같다.
         */
        post: operations["copy_to_bestiary_api_v1_game_bestiaries__bestiary_id__monsters_copies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/bestiaries/{bestiary_id}/monsters/{monster_id}": {
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
         * Delete Monster
         * @description 자기 도감의 몬스터를 지운다.
         */
        delete: operations["delete_monster_api_v1_game_bestiaries__bestiary_id__monsters__monster_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Monster
         * @description 자기 도감의 몬스터를 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_monster_api_v1_game_bestiaries__bestiary_id__monsters__monster_id__patch"];
        trace?: never;
    };
    "/api/v1/game/listings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Listings
         * @description 공개된 시나리오를 최근에 공개한 것부터 돌려준다. 장르, 태그, 함께 할 인원으로 거를 수 있다.
         *
         *     로그인하지 않아도 읽는다(#530). 그때는 전체 이용가만 나온다. 토큰을 보냈는데 틀렸으면 401 이다.
         */
        get: operations["list_listings_api_v1_game_listings_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/listings/{scenario_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Public Listing
         * @description 공개된 시나리오 하나를 돌려준다. 테이블을 만들기 전에 고를 것들(스타팅, 캐릭터 방식, 프리젠, 추천 모델)이 함께 있다.
         *
         *     로그인하지 않아도 읽는다(#530). 그때 성인용은 없는 것(404)이다.
         */
        get: operations["read_public_listing_api_v1_game_listings__scenario_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/lorebooks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Lorebooks
         * @description 자기 로어북의 목록을 최근에 만든 것부터 돌려준다.
         */
        get: operations["list_lorebooks_api_v1_game_lorebooks_get"];
        put?: never;
        /**
         * Create Lorebook
         * @description 로어북을 만든다. 항목은 만든 뒤에 하나씩 더한다.
         */
        post: operations["create_lorebook_api_v1_game_lorebooks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/lorebooks/{lorebook_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Lorebook
         * @description 자기 로어북 하나를 돌려준다. 항목은 싣지 않는다. 항목은 항목의 주소에서 읽는다.
         */
        get: operations["read_lorebook_api_v1_game_lorebooks__lorebook_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Lorebook
         * @description 자기 로어북을 지운다.
         */
        delete: operations["delete_lorebook_api_v1_game_lorebooks__lorebook_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Lorebook
         * @description 자기 로어북을 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_lorebook_api_v1_game_lorebooks__lorebook_id__patch"];
        trace?: never;
    };
    "/api/v1/game/lorebooks/{lorebook_id}/entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Entries
         * @description 자기 로어북의 항목을 만든 순서대로 전부 돌려준다.
         */
        get: operations["list_entries_api_v1_game_lorebooks__lorebook_id__entries_get"];
        put?: never;
        /**
         * Add Entry
         * @description 자기 로어북에 항목을 더한다.
         */
        post: operations["add_entry_api_v1_game_lorebooks__lorebook_id__entries_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/lorebooks/{lorebook_id}/entries/copies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Copy To Lorebook
         * @description 고른 참고 자료를 자기 로어북의 항목으로 복사한다. 물건은 물건, 몬스터는 종족 항목이다.
         *
         *     이미 복사해 둔 줄은 건너뛴다(skipped). 다 넣으면 상한을 넘으면 하나도 넣지 않고 409 다.
         *     없는 줄이 있으면 404(reference_not_found)다.
         */
        post: operations["copy_to_lorebook_api_v1_game_lorebooks__lorebook_id__entries_copies_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/lorebooks/{lorebook_id}/entries/{entry_id}": {
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
         * Delete Entry
         * @description 자기 로어북의 항목을 지운다.
         */
        delete: operations["delete_entry_api_v1_game_lorebooks__lorebook_id__entries__entry_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Entry
         * @description 자기 로어북의 항목을 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_entry_api_v1_game_lorebooks__lorebook_id__entries__entry_id__patch"];
        trace?: never;
    };
    "/api/v1/game/me": {
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
        get: operations["read_me_api_v1_game_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/personas": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Personas
         * @description 내 보관함. 최근에 만든 것부터.
         */
        get: operations["list_personas_api_v1_game_personas_get"];
        put?: never;
        /**
         * Create Persona
         * @description 보관함에 캐릭터를 만든다.
         */
        post: operations["create_persona_api_v1_game_personas_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/personas/{persona_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Persona
         * @description 보관한 캐릭터 하나.
         */
        get: operations["read_persona_api_v1_game_personas__persona_id__get"];
        /**
         * Update Persona
         * @description 보관한 캐릭터를 고친다. 보낸 것으로 통째로 바뀐다. 가져간 테이블은 바뀌지 않는다.
         */
        put: operations["update_persona_api_v1_game_personas__persona_id__put"];
        post?: never;
        /**
         * Delete Persona
         * @description 보관한 캐릭터를 지운다. 가져간 테이블은 바뀌지 않는다.
         */
        delete: operations["delete_persona_api_v1_game_personas__persona_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search References
         * @description 참고 자료를 이름(한국어 이름, 원본의 이름, 다른 이름)으로 찾는다. q 가 비면 전부다. kind 로 종류를 거른다.
         *
         *     보이는 이름의 차례다. 쪽마다 출처 표시(attributions)가 함께 온다.
         */
        get: operations["search_references_api_v1_game_references_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/rulebooks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Rulebooks
         * @description 자기 룰북의 목록을 최근에 만든 것부터 돌려준다.
         */
        get: operations["list_rulebooks_api_v1_game_rulebooks_get"];
        put?: never;
        /**
         * Create Rulebook
         * @description 룰북을 만든다. 만든 사람은 요청의 본문이 아니라 토큰에서 정해진다.
         */
        post: operations["create_rulebook_api_v1_game_rulebooks_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/rulebooks/templates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Templates
         * @description 룰북을 만들 때 고를 수 있는 템플릿들과 그 규칙(#615). 다른 주소처럼 로그인을 요구한다(user 는 쓰지 않는다).
         *
         *     룰북의 길(/{rulebook_id})보다 먼저 등록한다. templates 를 룰북의 id 로 읽지 않게 한다.
         */
        get: operations["list_templates_api_v1_game_rulebooks_templates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/rulebooks/{rulebook_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Rulebook
         * @description 자기 룰북 하나를 돌려준다.
         */
        get: operations["read_rulebook_api_v1_game_rulebooks__rulebook_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Rulebook
         * @description 자기 룰북을 지운다.
         */
        delete: operations["delete_rulebook_api_v1_game_rulebooks__rulebook_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Rulebook
         * @description 자기 룰북을 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_rulebook_api_v1_game_rulebooks__rulebook_id__patch"];
        trace?: never;
    };
    "/api/v1/game/scenarios": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Scenarios
         * @description 자기 시나리오의 목록을 최근에 만든 것부터 돌려준다. 등급을 함께 싣는다.
         */
        get: operations["list_scenarios_api_v1_game_scenarios_get"];
        put?: never;
        /**
         * Create Scenario
         * @description 시나리오를 만든다. 룰북, 세계관, 로어북은 자기 것만 가리킬 수 있다. 추천 서술 모델을 반드시 고른다.
         */
        post: operations["create_scenario_api_v1_game_scenarios_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Scenario
         * @description 자기 시나리오 하나를 돌려준다. 추천 서술 모델의 상태를 함께 싣는다.
         */
        get: operations["read_scenario_api_v1_game_scenarios__scenario_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete Scenario
         * @description 자기 시나리오를 지운다.
         */
        delete: operations["delete_scenario_api_v1_game_scenarios__scenario_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update Scenario
         * @description 자기 시나리오를 고친다. 보낸 칸만 바뀐다. 룰북과 세계관은 null 로 떼고, 로어북은 목록을 통째로 바꾼다.
         */
        patch: operations["update_scenario_api_v1_game_scenarios__scenario_id__patch"];
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/listing": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Listing
         * @description 자기 시나리오의 공개 정보를 돌려준다. 아직 쓰지 않았으면 빈 것을 돌려준다.
         */
        get: operations["read_listing_api_v1_game_scenarios__scenario_id__listing_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update Listing
         * @description 자기 시나리오의 소개 페이지를 고친다. 보낸 칸만 바뀐다. 판을 새로 내지 않아도 된다.
         */
        patch: operations["update_listing_api_v1_game_scenarios__scenario_id__listing_patch"];
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/listing/publication": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set Publication
         * @description 공개할 판을 정한다. 시나리오 하나에 공개 판은 하나다. version 을 null 로 보내면 공개를 내린다.
         */
        put: operations["set_publication_api_v1_game_scenarios__scenario_id__listing_publication_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/monsters/{monster_id}/sheet-proposal": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Propose Monster Sheet
         * @description 참고 자료(SRD)에서 복사한 몬스터에 시나리오의 룰북으로 시트를 제안한다. 저장하지 않는다.
         *
         *     sheet 는 시나리오의 monster_sheets 에 그대로 넣을 수 있다. notes 는 원본과 다르게 옮긴 것들이다.
         *     몬스터는 시나리오에 붙인 도감의 것이어야 한다(아니면 404). 룰북이 없으면 409(no_rulebook),
         *     복사한 몬스터가 아니면 422(not_copied), 룰북의 능력치가 SRD 와 다르면 422(rules_not_srd)다.
         */
        get: operations["propose_monster_sheet_api_v1_game_scenarios__scenario_id__monsters__monster_id__sheet_proposal_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/publish-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Check Publishable
         * @description 자기 시나리오를 지금 게시하면 막히는 이유를 미리 본다(#428). 판을 만들지 않는다.
         *
         *     게시(POST /versions)와 같은 검사다. 게시가 409 의 problems 로 돌려줄 것을 200 으로 돌려준다.
         */
        get: operations["check_publishable_api_v1_game_scenarios__scenario_id__publish_check_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Versions
         * @description 자기 시나리오의 판을 최근 것부터 돌려준다. 굳힌 내용은 싣지 않는다.
         */
        get: operations["list_versions_api_v1_game_scenarios__scenario_id__versions_get"];
        put?: never;
        /**
         * Publish Scenario
         * @description 자기 시나리오를 게시한다. 지금의 내용이 새 판으로 굳는다.
         *
         *     판의 로어북 항목은 뒤에서 벡터로 바뀐다. 응답은 그것을 기다리지 않는다.
         */
        post: operations["publish_scenario_api_v1_game_scenarios__scenario_id__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/scenarios/{scenario_id}/versions/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Version
         * @description 자기 시나리오의 판 하나를 굳힌 내용과 함께 돌려준다.
         */
        get: operations["read_version_api_v1_game_scenarios__scenario_id__versions__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/service/users/{public_id}/withdrawal": {
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
         * @description 탈퇴한 사람을 게임에서 정리한다.
         */
        post: operations["receive_withdrawal_api_v1_game_service_users__public_id__withdrawal_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Tables
         * @description 내가 앉아 있는 테이블을 최근에 만든 것부터 돌려준다.
         */
        get: operations["list_tables_api_v1_game_tables_get"];
        put?: never;
        /**
         * Create Table
         * @description 테이블을 만든다. 만든 사람이 방장이 되어 앉는다.
         *
         *     서술 모델은 고른 것, 아니면 시나리오의 추천 모델, 쓸 수 없으면 같은 회사의 대체 모델이다.
         *     셋 다 없으면 422(narration_model)다. 방장이 모델을 골라 다시 보낸다.
         */
        post: operations["create_table_api_v1_game_tables_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/join": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Join Table
         * @description 초대 코드로 테이블에 들어가 앉는다.
         */
        post: operations["join_table_api_v1_game_tables_join_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/lobby": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Lobby
         * @description 로비. 들어갈 수 있는 테이블을 최근에 만든 것부터 돌려준다. 모집 중이고 자리가 남은 것만 나온다.
         */
        get: operations["list_lobby_api_v1_game_tables_lobby_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/narration-models": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Narration Models
         * @description 테이블의 서술 모델로 고를 수 있는 모델들과 1인 1라운드의 값. 로그인한 사람에게만 보인다(가격 수집 막기).
         *
         *     모델 목록에서 켜져 있고 결제 서버가 지금 파는 모델만 나온다. 값이 바뀌는 예약이 있으면 next 에 싣는다.
         */
        get: operations["list_narration_models_api_v1_game_tables_narration_models_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/past": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Past Tables
         * @description 내가 떠난 테이블들. 최근에 떠난 것부터다. 시작한 테이블에서 떠난 것만 있다.
         */
        get: operations["list_past_tables_api_v1_game_tables_past_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/past/{table_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Past Events
         * @description 떠난 테이블의 이벤트를 떠난 때까지만 일어난 순서대로 돌려준다. 앉은 사람의 길(.../events)과 모양이 같다.
         *
         *     last_sequence 는 떠났다는 이벤트의 번호다. 테이블의 마지막 번호가 아니다. 그 뒤로는 더 오지 않는다.
         */
        get: operations["list_past_events_api_v1_game_tables_past__table_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/past/{table_id}/transcript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Past Transcript
         * @description 떠난 테이블의 기록. 떠났다는 이벤트까지다. 떠난 적이 없으면 404.
         */
        get: operations["download_past_transcript_api_v1_game_tables_past__table_id__transcript_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Table
         * @description 내가 앉아 있는 테이블 하나를 돌려준다.
         */
        get: operations["read_table_api_v1_game_tables__table_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/character": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set Character
         * @description 내 캐릭터를 정한다. 직접 만들거나 프리젠을 가져온다. 모집 중에만 된다.
         */
        put: operations["set_character_api_v1_game_tables__table_id__character_put"];
        /**
         * Bring In Character
         * @description 죽은 내 캐릭터의 뒤를 이을 새 캐릭터를 들인다. 진행 중인 테이블에서, 내 캐릭터가 죽었을 때만 된다.
         *
         *     받는 값은 캐릭터를 정할 때와 같다. 새 캐릭터는 시트를 바로 받고, 다음 라운드부터 선언을 낸다.
         *     주사위로 정하는 방식이면 먼저 새로 굴린다(POST .../character/roll).
         */
        post: operations["bring_in_character_api_v1_game_tables__table_id__character_post"];
        /**
         * Give Up Character
         * @description 쓰러진 내 캐릭터를 스스로 보낸다. 캐릭터가 죽는다. 되돌릴 수 없다.
         *
         *     진행 중인 테이블에서, 캐릭터가 쓰러져 있을 때만 된다. 죽음의 굴림을 기다리지 않고 새 캐릭터로 넘어가려는 때 쓴다.
         *     라운드를 닫으러 보지 않는다. 쓰러진 사람은 원래 라운드가 기다리지 않으므로, 보내도 기다릴 사람이 줄지 않는다.
         */
        delete: operations["give_up_character_api_v1_game_tables__table_id__character_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/character/persona": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Keep Character
         * @description 이 테이블의 내 캐릭터를 내 보관함에 저장한다. 이름, 설명, 시작할 때의 능력치를 저장한다.
         *
         *     프리젠은 저장하지 못한다. 저장한 것은 사본이라, 그 뒤에 테이블에서 바뀐 것은 보관함으로 오지 않는다.
         */
        post: operations["keep_character_api_v1_game_tables__table_id__character_persona_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/character/roll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Roll Abilities
         * @description 내 능력치의 점수를 주사위로 굴린다. 본문이 없다. 굴리는 것은 서버다.
         *
         *     캐릭터 하나에 한 번만 된다. 굴린 점수는 응답의 members[].roll 에 있다. 그것을 능력치에 놓아 캐릭터를 정한다.
         *     진행 중에는 캐릭터가 죽은 사람이 새 캐릭터를 위해 굴린다.
         */
        post: operations["roll_abilities_api_v1_game_tables__table_id__character_roll_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/clock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Clock
         * @description 테이블의 게임 안의 지금 시각과 다음 라운드가 열릴 때 흐를 시간. 앉은 사람 모두가 본다.
         *
         *     시작 전에는 판의 시작 시각이다. 라운드가 열릴 때마다 흐른다(첫 라운드는 시작 시각에 열린다).
         */
        get: operations["get_clock_api_v1_game_tables__table_id__clock_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/credit-wait": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Credit Wait
         * @description 크레딧이 모자란 사람을 기다리는 시간(초)과, 지나면 그 사람을 자리에서 빼는지를 바꾼다. 방장만 한다.
         *
         *     진행 중에도 된다. 지금 기다리는 라운드에도 바로 쓴다.
         */
        put: operations["change_credit_wait_api_v1_game_tables__table_id__credit_wait_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/end": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * End Table
         * @description 테이블을 끝낸다.
         */
        post: operations["end_table_api_v1_game_tables__table_id__end_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/equipment": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Wear Equipment
         * @description 자기 캐릭터가 가진 물건 하나를 장비의 칸들에 끼운다(#276). 찬 칸의 것은 벗겨진다. 라운드의 행동이 아니다.
         *
         *     선언을 받는 중에만 된다(닫는 중이면 409 round_closing). 쓰러졌거나 죽었으면 409.
         *     착용하지 않는 물건이나 판에 없는 물건이면 422(entry_id), 칸이 맞지 않으면 422(slots),
         *     가지고 있지 않으면 409(not_enough_items). 모두에게 이벤트(equipment_changed)가 간다.
         */
        put: operations["wear_equipment_api_v1_game_tables__table_id__equipment_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/equipment/{slot}": {
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
         * Take Off Equipment
         * @description 자기 캐릭터의 그 칸을 비운다(#276). 그 칸을 차지한 착용이 통째로 빠진다. 비어 있으면 그대로 돌려준다.
         *
         *     선언을 받는 중에만 된다(닫는 중이면 409 round_closing). 쓰러졌거나 죽었으면 409.
         */
        delete: operations["take_off_equipment_api_v1_game_tables__table_id__equipment__slot__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Events
         * @description 테이블의 이벤트를 일어난 순서대로 돌려준다. after 를 주면 그 번호 뒤의 것만 온다.
         *
         *     처음에는 after 없이 읽고, 그 뒤로는 마지막으로 받은 번호를 after 로 준다. 못 본 것만 받는다.
         */
        get: operations["list_events_api_v1_game_tables__table_id__events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/friendly-fire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Friendly Fire
         * @description 앉은 사람끼리 해칠 수 있는 정도(#803)를 바꾼다. 방장만 한다. 진행 중에도 된다.
         *
         *     끔(off), 장난만(prank), 다 됨(full)이다. 맞는 쪽이 받아들이는 정도와 견주어 낮은 쪽이 든다.
         *     이미 받은 선언도 라운드를 닫을 때 다시 본다.
         */
        put: operations["change_friendly_fire_api_v1_game_tables__table_id__friendly_fire_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/host": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Transfer Host
         * @description 방장을 다른 참가자에게 넘긴다.
         */
        put: operations["transfer_host_api_v1_game_tables__table_id__host_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/join": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Join Public Table
         * @description 로비에 보이는 테이블에 들어가 앉는다. 비밀번호가 걸려 있으면 비밀번호를 보낸다.
         *
         *     비밀번호를 너무 많이 틀리면 한동안 429 다(app/tables/password_attempts.py).
         */
        post: operations["join_public_table_api_v1_game_tables__table_id__join_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/members/me": {
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
         * Leave Table
         * @description 테이블에서 나간다. 방장이 나가면 가장 먼저 들어온 사람이 방장이 된다.
         *
         *     진행 중이면, 나간 사람만 내지 않았던 라운드를 닫기 시작한다. 남은 사람이 기다리지 않게 한다.
         */
        delete: operations["leave_table_api_v1_game_tables__table_id__members_me_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/members/me/friendly-fire": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Friendly Fire Consent
         * @description 자기를 겨누는 것(동료의 피해)을 받아들이는 정도(#803)를 바꾼다. 앉은 사람이 자기 것만 바꾼다. 언제든 된다.
         *
         *     끔이 기본이다. 테이블이 다 됨이어도 받아들이기 전에는 아무도 해치지 못한다.
         */
        put: operations["change_friendly_fire_consent_api_v1_game_tables__table_id__members_me_friendly_fire_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/members/{user_id}": {
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
         * Kick Member
         * @description 참가자를 내보낸다. 초대 코드가 새로 만들어진다. 응답에 새 코드가 실린다.
         *
         *     진행 중이면, 내보낸 사람만 내지 않았던 라운드를 닫기 시작한다.
         */
        delete: operations["kick_member_api_v1_game_tables__table_id__members__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/members/{user_id}/reroll": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Grant Reroll
         * @description 참가자 한 사람에게 "한 번 더 굴리기"를 준다. 시나리오의 제작자가 허락한 테이블에서만 된다.
         */
        post: operations["grant_reroll_api_v1_game_tables__table_id__members__user_id__reroll_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Messages
         * @description 테이블의 채팅을 쓴 순서대로 돌려준다. after 를 주면 그 번호 뒤의 것만 온다.
         *
         *     처음에는 after 없이 읽고, 그 뒤로는 마지막으로 받은 번호를 after 로 준다. 못 본 것만 받는다.
         */
        get: operations["list_messages_api_v1_game_tables__table_id__messages_get"];
        put?: never;
        /**
         * Post Message
         * @description 채팅을 쓴다. 모집 중과 진행 중에 쓸 수 있다. 끝난 테이블에는 쓸 수 없다.
         */
        post: operations["post_message_api_v1_game_tables__table_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/messages/typing": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Announce Typing
         * @description "입력 중"이라고 알린다. 저장하지 않는다. 다른 사람들의 스트림에 typing 메시지가 간다.
         *
         *     화면은 사용자가 글자를 치는 동안 3초쯤에 한 번 부른다. 멈췄다는 것은 알리지 않는다.
         *     받는 쪽이 5초쯤 뒤에 스스로 지운다.
         */
        post: operations["announce_typing_api_v1_game_tables__table_id__messages_typing_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/narration-model": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Narration Model
         * @description 서술 모델을 바꾼다. 방장만 한다. 고를 수 있는 모델만 된다(GET /tables/narration-models).
         *
         *     진행 중에도 된다. 바꾼 값은 다음 라운드부터 쓴다.
         *     다만 아직 서술하지 않은 지금 라운드(선언을 받는 중이거나 서술이 실패해 멈춤)는 함께 바꾸고 새 값으로 다시 건다.
         */
        put: operations["change_narration_model_api_v1_game_tables__table_id__narration_model_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/narration-style": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Narration Style
         * @description GM 의 서술 문체를 바꾼다. 방장만 한다. 진행 중에도 되고, 다음 서술부터 쓴다. null 이면 시나리오의 추천 문체로.
         */
        put: operations["change_narration_style_api_v1_game_tables__table_id__narration_style_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/references": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change References
         * @description 서술에 참고 자료(SRD 같은 바깥 자료)를 넣을지 바꾼다. 방장만 한다. 모집 중에만 된다(시작하면 고정이다).
         *
         *     켜려면 판의 세계관이 허용해야 한다. 아니면 422 다.
         */
        put: operations["change_references_api_v1_game_tables__table_id__references_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/round-time-limit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Round Time Limit
         * @description 라운드의 시간 제한(초)을 바꾼다. 방장만 한다. null 이면 시간 제한을 없앤다.
         *
         *     진행 중에도 된다. 바꾼 값은 다음 라운드부터 쓴다. 지금 열린 라운드의 마감은 그대로다.
         */
        put: operations["change_round_time_limit_api_v1_game_tables__table_id__round_time_limit_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Rounds
         * @description 테이블의 라운드를 처음 것부터 돌려준다. 지나간 이야기를 순서대로 읽는다.
         */
        get: operations["list_rounds_api_v1_game_tables__table_id__rounds_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/current": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Current Round
         * @description 가장 최근 라운드를 돌려준다. 진행 중인 테이블에서는 지금 선언을 받고 있는 라운드다.
         */
        get: operations["read_current_round_api_v1_game_tables__table_id__rounds_current_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/current/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Close Round
         * @description 방장이 라운드를 닫는다. 선언을 기다리지 않고 넘어간다. status 가 closing 인 라운드가 돌아온다.
         *
         *     닫는 중인 채로 오래 멈춰 있는 라운드에 다시 부르면 서술을 다시 맡긴다. 판정은 다시 하지 않는다.
         */
        post: operations["close_round_api_v1_game_tables__table_id__rounds_current_close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/current/declaration": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Declare
         * @description 열려 있는 라운드에 선언을 낸다. 다시 내면 바뀐다.
         *
         *     모두가 내면 라운드가 닫기 시작한다. 그때는 status 가 closing 인 라운드가 돌아온다.
         *     행동을 붙인 선언은 그때 판정된다. 결과가 선언의 outcome 에 실려 돌아온다.
         *     GM 의 서술은 뒤에서 돈다. 끝나서 다음 라운드가 열린 것은 스트림으로 온다.
         */
        put: operations["declare_api_v1_game_tables__table_id__rounds_current_declaration_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/current/people": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Scene Cast
         * @description 가장 최근 라운드의 장면에 나온 인물들을 돌려준다. 행동의 npc 칸에 이 목록의 id 를 적는다.
         *
         *     자리가 있는 인물은 살아 있는 캐릭터가 서 있는 장소들의 인물, 없는 인물은 장면에 이름이나 호칭이 나온 인물만
         *     들어간다(#282). 테이블의 인물 전부가 아니다.
         */
        get: operations["read_scene_cast_api_v1_game_tables__table_id__rounds_current_people_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/{number}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Round
         * @description 라운드 하나를 번호로 돌려준다.
         */
        get: operations["read_round_api_v1_game_tables__table_id__rounds__number__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/rounds/{number}/charges": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Round Charges
         * @description 라운드의 서술 값을 내는 사람마다의 청구. 앉은 사람만 본다. 라운드를 열 때 앉아 있던 사람 모두다.
         *
         *     값(credits)은 결제 서버가 실제로 홀드한 값이다. 라운드를 연 뒤 몇 초 안에 걸린다. 그 전에는 null 이다.
         *     이 기록이 생기기 전에 연 라운드나 결제 서버 없이 도는 서버면 빈 목록이다.
         */
        get: operations["read_round_charges_api_v1_game_tables__table_id__rounds__number__charges_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Start Table
         * @description 테이블을 시작한다. 모든 참가자가 캐릭터를 만들어 둬야 한다.
         *
         *     첫 라운드에 1인 1라운드의 값을 알린다(app/rounds/round_price.py).
         *     첫 라운드를 연 뒤 서술 모델의 은퇴를 본다(app/tables/retirement_watch.py). 은퇴했으면 바뀐 모델로 답한다.
         */
        post: operations["start_table_api_v1_game_tables__table_id__start_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Open Stream
         * @description 테이블의 스트림을 연다. 새 이벤트(table_event)와 새 채팅(chat_message), 자기 쪽지함의 새 쪽지(whisper)가
         *     생기는 대로 온다.
         *
         *     처음에는 REST 로 지금까지의 것을 읽고, 그 마지막 번호를 events_after, messages_after, whispers_after 에 적어 붙는다.
         *     끊겼다 다시 붙을 때는 마지막으로 받은 메시지의 id 를 Last-Event-ID 머리말로 보낸다.
         *
         *     서버가 닫을 때는 이유를 담은 closed 메시지를 보내고 끝낸다(not_seated, table_ended, token_expired).
         */
        get: operations["open_stream_api_v1_game_tables__table_id__stream_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/transcript": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Download Transcript
         * @description 앉아 있는 테이블의 기록. 받기 시작한 때의 마지막 이벤트까지다. 앉지 않았으면 404.
         */
        get: operations["download_transcript_api_v1_game_tables__table_id__transcript_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/whisper-notice": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Change Whisper Notice
         * @description 쪽지를 보낸 사실을 모두에게 알릴지 바꾼다. 방장만 한다.
         *
         *     켜면 쪽지를 보낼 때마다 "누가 누구에게 보냈다"가 이벤트(whisper_sent)로 간다. 글은 가지 않는다.
         *     진행 중에도 된다. 바꾼 뒤에 보내는 쪽지부터 따른다.
         */
        put: operations["change_whisper_notice_api_v1_game_tables__table_id__whisper_notice_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/tables/{table_id}/whispers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Whispers
         * @description 자기 쪽지함의 쪽지를 순서대로 돌려준다. 보낸 것과 받은 것이 함께 온다. after 를 주면 그 번호 뒤의 것만 온다.
         *
         *     번호는 쪽지함마다 센다. 채팅의 번호와 따로다.
         */
        get: operations["list_whispers_api_v1_game_tables__table_id__whispers_get"];
        put?: never;
        /**
         * Post Whisper
         * @description 같은 테이블에 앉은 한 사람에게 쪽지를 보낸다. 보낸 사람과 받은 사람만 본다. 방장도 보지 못한다.
         *
         *     gm_visible 이면 GM(AI)도 그 라운드의 서술에서 숨은 정보로 본다. 서술은 모두에게 나가므로 내용이 새어 나갈 수 있다.
         *     테이블이 알리기로 했으면(whisper_notice) 보냈다는 사실만 이벤트(whisper_sent)로 모두에게 간다.
         */
        post: operations["post_whisper_api_v1_game_tables__table_id__whispers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/worlds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Worlds
         * @description 자기 세계관의 목록을 최근에 만든 것부터 돌려준다.
         */
        get: operations["list_worlds_api_v1_game_worlds_get"];
        put?: never;
        /**
         * Create World
         * @description 세계관을 만든다. 만든 사람은 요청의 본문이 아니라 토큰에서 정해진다.
         */
        post: operations["create_world_api_v1_game_worlds_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/game/worlds/{world_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read World
         * @description 자기 세계관 하나를 돌려준다.
         */
        get: operations["read_world_api_v1_game_worlds__world_id__get"];
        put?: never;
        post?: never;
        /**
         * Delete World
         * @description 자기 세계관을 지운다.
         */
        delete: operations["delete_world_api_v1_game_worlds__world_id__delete"];
        options?: never;
        head?: never;
        /**
         * Update World
         * @description 자기 세계관을 고친다. 보낸 칸만 바뀐다.
         */
        patch: operations["update_world_api_v1_game_worlds__world_id__patch"];
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
         * @description 기대는 것들에 3초 안에 모두 닿으면 200, 아니면 503 을 돌려준다.
         *
         *     왜 닿지 않는지는 응답에 싣지 않는다. 오류 문구에는 DB 와 Redis 의 주소, 계정 이름이 들어 있다.
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
         * Ability
         * @description 능력치 하나. 예: 근력.
         */
        Ability: {
            /** Key */
            key: string;
            /** Name */
            name: string;
        };
        /**
         * ActionRequest
         * @description 제재를 할 때 받는 값(#392). 사유만 받는다. 누가 했는지는 토큰에서 읽는다.
         */
        ActionRequest: {
            /** Reason */
            reason: string;
        };
        /**
         * AdjustEffect
         * @description 수치 하나(resource, 룰북의 resources 의 이름표)를 양(amount)만큼 올리거나(양수) 내린다(음수, #804).
         *
         *     내리는 것에는 성질(nature, 룰북의 natures 의 이름표) 하나를 달 수 있다(#886 ②). 맞는 쪽이 그 성질에 저항하거나
         *     면역이면 내리지 않는다. 비우면 누구나 받는다. 올리는 것은 해롭지 않아 막을 일이 없다. 성질을 달지 않는다.
         */
        AdjustEffect: {
            /** Amount */
            amount: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "adjust";
            /** Nature */
            nature?: string | null;
            /** Resource */
            resource: string;
        };
        /**
         * AidAct
         * @description 거드는 행동.
         * @enum {string}
         */
        AidAct: "treat" | "pick" | "repair" | "force" | "cross";
        /**
         * AidOut
         * @description 행동의 판정에 붙여 쓴 물건(#277, #802, 거들기). 판정의 보정(modifier)에 bonus 가 이미 들었다.
         *
         *     치료, 따기, 부수기, 고치기, 넘기에 붙는다.
         */
        AidOut: {
            /**
             * Act
             * @default treat
             */
            act: string;
            /** Bonus */
            bonus: number;
            /**
             * Broken
             * @default false
             */
            broken: boolean;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Lost
             * @default false
             */
            lost: boolean;
            /** Name */
            name: string;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            /** Used */
            used: boolean;
        };
        /**
         * AidWear
         * @description 거든 물건이 굴린 뒤에 어떻게 되나.
         * @enum {string}
         */
        AidWear: "always" | "on_fail" | "never";
        /**
         * Armor
         * @description 방어구의 규칙(#276). 어떤 방식으로 막는지다. 방어의 크기는 판의 아이템 규칙과 몬스터 시트가 정한다.
         *
         *     save_target 은 세이브의 목표값이다. save 방식에만 적는다.
         *     pierce_base 는 관통의 기준값이다. 관통력(ap)이 있는 무기로 칠 때 쓴다. 방식을 가리지 않는다.
         */
        Armor: {
            mode: components["schemas"]["ArmorMode"];
            /**
             * Pierce Base
             * @default 10
             */
            pierce_base: number;
            /** Save Target */
            save_target?: number | null;
        };
        /**
         * ArmorMode
         * @description 방어구가 공격을 막는 방식(#276). 룰북이 고른다.
         * @enum {string}
         */
        ArmorMode: "ac" | "reduce" | "save";
        /**
         * ArrivalOut
         * @description 이 라운드에 새로 들어온 캐릭터 하나. 캐릭터가 죽은 플레이어가 들인 새 캐릭터다.
         */
        ArrivalOut: {
            /** Character Name */
            character_name: string;
            /** Replaces */
            replaces: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * AssetPage
         * @description 자산 목록의 한 쪽.
         */
        AssetPage: {
            /** Items */
            items: components["schemas"]["AssetSummary"][];
            /** Total */
            total: number;
        };
        /**
         * AssetSummary
         * @description 목록에 싣는 값. 어느 종류든 같다. 종류별 긴 글은 싣지 않는다.
         */
        AssetSummary: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * AttackSnapshot
         * @description 몬스터의 공격 하나. 이름표(능력치, 난이도, 양의 등급)는 판 안의 규칙의 것이다.
         */
        AttackSnapshot: {
            /** Ability */
            ability: string;
            cost?: components["schemas"]["SkillCost"] | null;
            /** Difficulty */
            difficulty: string;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /** Harm */
            harm?: string | null;
            /** Name */
            name: string;
            /** Nature */
            nature?: string | null;
            /** Weapon */
            weapon?: string | null;
        };
        /**
         * AttitudeChangeOut
         * @description 엔진이 바꾼 NPC 의 태도. 앞의 태도, 바뀐 태도, 까닭(caught_stealing 훔치다 들킴).
         */
        AttitudeChangeOut: {
            attitude: components["schemas"]["NpcAttitude"];
            previous: components["schemas"]["NpcAttitude"];
            /** Reason */
            reason: string;
        };
        /**
         * BarSnapshot
         * @description 길의 빗장(#281). 있는 쪽(길의 한 끝)과 시작할 때 걸려 있는가.
         */
        BarSnapshot: {
            /**
             * Barred
             * @default false
             */
            barred: boolean;
            /**
             * Side
             * Format: uuid
             */
            side: string;
        };
        /**
         * BestiaryCreate
         * @description 도감을 만들 때 받는 값. 공통 칸뿐이다. 몬스터는 만든 뒤에 하나씩 더한다.
         */
        BestiaryCreate: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Title */
            title: string;
        };
        /**
         * BestiaryUpdate
         * @description 도감을 고칠 때 받는 값. 공통 칸뿐이다.
         */
        BestiaryUpdate: {
            /** Description */
            description?: string | null;
            /** Title */
            title?: string | null;
        };
        /**
         * BlowOut
         * @description 타격에 장비가 든 것(#276). 엔진이 정했다. 무기, 맞은 부위, 노렸는가, 그 부위의 방어다.
         *
         *     mode 는 룰북의 방어 방식이다. ac 면 방어가 목표값(target)에 이미 더해졌고, reduce 면 피해에서 빠졌다
         *     (변화의 rolls 를 더한 값과 amount 의 차이). 방어 방식이 없는 규칙이면 None 이고 부위도 없다.
         */
        BlowOut: {
            /** Aimed */
            aimed: boolean;
            /** Defense */
            defense: number;
            /** Location */
            location: string | null;
            /** Location Name */
            location_name: string | null;
            /** Mode */
            mode: string | null;
            pierce?: components["schemas"]["PierceOut"] | null;
            save?: components["schemas"]["SaveOut"] | null;
            weapon: components["schemas"]["BlowWeaponOut"] | null;
        };
        /**
         * BlowWeaponOut
         * @description 타격에 쓴 무기(#276). 판의 물건과 그 이름과 판정의 보정에 더한 공격 보정이다.
         */
        BlowWeaponOut: {
            /**
             * Ap
             * @default 0
             */
            ap: number;
            /** Bonus */
            bonus: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
        };
        /**
         * BuyAction
         * @description 이번 장면의 상인(npc)에게서 물건(item) count 개를 사는 행동(app/rounds/trades.py, #278).
         *
         *     판정이 없다. 값은 판의 물건의 값 × 개수다. 상인의 소지품에 그만큼 있어야 하고(재고), 돈이 모자라면 사지 못한다.
         *     다 사거나 하나도 사지 않는다. 사려던 것보다 적게 사서 돈이 엉뚱하게 남는 일을 만들지 않는다.
         */
        BuyAction: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "buy";
            /**
             * Npc
             * Format: uuid
             */
            npc: string;
        };
        /**
         * CalledShot
         * @description 노려 치기의 어려움. 목표값을 올리는 크기(amount)는 그 방식에만 있다.
         */
        CalledShot: {
            /**
             * Amount
             * @default 0
             */
            amount: number;
            mode: components["schemas"]["CalledShotMode"];
        };
        /**
         * CalledShotMode
         * @description 노려 치기가 판정을 어렵게 하는 방식.
         * @enum {string}
         */
        CalledShotMode: "target_plus" | "disadvantage";
        /**
         * CalledShotOut
         * @description 노려 친 것. 무엇을 노렸는지와 판정이 얼마나 어려워졌는지다. 성공했으면 그 부상이 생긴다.
         */
        CalledShotOut: {
            /** Aim */
            aim: string;
            /** Amount */
            amount: number;
            /** Mode */
            mode: string;
        };
        /**
         * CarriedItem
         * @description 몬스터나 NPC 가 지닌 물건 한 줄. 붙인 로어북의 물건 항목(entry_id)을 count 개 지녔다. 몬스터는 마리마다다.
         *
         *     chance 는 살아 있던 몬스터나 NPC 가 처음 쓰러졌을 때 이 줄이 떨어질 확률(%)이다. 비우면 늘 떨어진다(100).
         *     줄마다 따로 굴린다. 떨어지지 않은 것은 그대로 지닌다.
         *     wear 는 그 물건 하나를 착용한 칸들이다(#276). 한 개라도 지니고 있는 동안 착용한 것이다.
         *     떨어뜨리거나 빼앗겨 남은 것이 없으면 그 부위는 빈다. 칸이 맞는지는 게시할 때 본다(carried_wear_invalid).
         *     항목이 붙인 로어북의 물건인지는 게시할 때 본다. 소지품과 같은 문제로 알린다(item_entry_missing, item_not_item).
         */
        "CarriedItem-Input": {
            /**
             * Chance
             * @default 100
             */
            chance: number;
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * CarriedItem
         * @description 몬스터나 NPC 가 지닌 물건 한 줄. 붙인 로어북의 물건 항목(entry_id)을 count 개 지녔다. 몬스터는 마리마다다.
         *
         *     chance 는 살아 있던 몬스터나 NPC 가 처음 쓰러졌을 때 이 줄이 떨어질 확률(%)이다. 비우면 늘 떨어진다(100).
         *     줄마다 따로 굴린다. 떨어지지 않은 것은 그대로 지닌다.
         *     wear 는 그 물건 하나를 착용한 칸들이다(#276). 한 개라도 지니고 있는 동안 착용한 것이다.
         *     떨어뜨리거나 빼앗겨 남은 것이 없으면 그 부위는 빈다. 칸이 맞는지는 게시할 때 본다(carried_wear_invalid).
         *     항목이 붙인 로어북의 물건인지는 게시할 때 본다. 소지품과 같은 문제로 알린다(item_entry_missing, item_not_item).
         */
        "CarriedItem-Output": {
            /**
             * Chance
             * @default 100
             */
            chance: number;
            /**
             * Count
             * @default 1
             */
            count: number;
            /** Entry Id */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * CarriedItemSnapshot
         * @description 몬스터나 NPC 가 지닌 물건 한 줄. 판 안의 로어북 물건 항목 하나(entry_id)를 count 개 지녔다. 몬스터는 마리마다다.
         *
         *     chance(%)는 처음 쓰러졌을 때 이 줄이 떨어질 확률이다.
         */
        CarriedItemSnapshot: {
            /** Chance */
            chance: number;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * CarriedOut
         * @description 몬스터 한 마리나 NPC 하나가 지금 지닌 물건 한 가지(app/tables/carried.py). 무엇을 몇 개, 장비인지 소지품인지.
         */
        CarriedOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Equipped */
            equipped: boolean;
            /** Name */
            name: string;
            /** Price */
            price?: number | null;
            rarity: components["schemas"]["ItemRarity"];
        };
        /**
         * CarryOut
         * @description 업고 간 결과(#367). 엔진이 정했다(app/rounds/map_actions.py).
         */
        CarryOut: {
            /** Carried */
            carried: boolean;
            /** Character Name */
            character_name: string | null;
            /** Reason */
            reason: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * CatalogItemOut
         * @description 판에 있는 물건 하나. 로어북의 물건 항목이다.
         *
         *     kind 가 consumable 이면 쓰면 하나 줄어든다. effects 는 쓰면 대상에게 일어나는 일들이다(#800, 차례대로):
         *     heal(HP 를 그 등급만큼 되돌림), cure(적은 부상을 풂), damage(그 등급만큼 피해), injure(부상 하나를 입힘).
         *     등급은 rules 의 magnitudes, 부상은 rules 의 injuries 의 key 다. 피해나 부상이 있으면 동료에게는 쓰지 못한다.
         */
        CatalogItemOut: {
            /**
             * Aids
             * @default []
             */
            aids: components["schemas"]["ItemAid"][];
            /** Ap */
            ap?: number | null;
            /** Attack */
            attack?: number | null;
            /** Defense */
            defense?: number | null;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Guard */
            guard?: number | null;
            kind: components["schemas"]["ItemKind"];
            /**
             * Lock
             * @default false
             */
            lock: boolean;
            /** Name */
            name: string;
            /** Nature */
            nature?: string | null;
            /** Price */
            price?: number | null;
            rarity: components["schemas"]["ItemRarity"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Slot Count
             * @default 1
             */
            slot_count: number;
            /**
             * Slots
             * @default []
             */
            slots: string[];
            throw?: components["schemas"]["app__tables__schemas__ItemThrowOut"] | null;
            trap?: components["schemas"]["ItemTrapOut"] | null;
            /** Ward */
            ward?: number | null;
        };
        /**
         * ChangeKind
         * @description HP 가 바뀌는 방향.
         * @enum {string}
         */
        ChangeKind: "damage" | "recovery";
        /**
         * CharacterMode
         * @description 테이블에 앉는 사람이 캐릭터를 얻는 방식.
         *
         *     시나리오의 제작자가 허용할 방식을 고른다. 방장은 그 안에서 테이블의 설정으로 더 좁힐 수 있다.
         * @enum {string}
         */
        CharacterMode: "pregen" | "custom" | "manual" | "point_buy" | "rolled";
        /**
         * CharacterOut
         * @description 캐릭터.
         */
        CharacterOut: {
            /** Description */
            description: string;
            /** Name */
            name: string;
        };
        /**
         * CharacterSheet
         * @description 캐릭터(앉은 사람)의 시트. 기본 시트와 프리젠의 시트다. 아는 기술(#805)과 저항(#886 ②)이 더 있다.
         *     NPC 와 몬스터의 시트에는 없다(NPC 의 저항은 NPC 시트에 적는다).
         *
         *     skills 는 룰북의 기술(rules.skills)의 이름표다. 비우면 아는 기술이 없다. 맞는지는 게시할 때 본다(knows_only).
         *     resistances 는 타고난 저항이다(#886 ②). 성질이 룰북의 것인지는 게시할 때 본다(resists_only_known).
         */
        CharacterSheet: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            };
            /** Max Hp */
            max_hp: number;
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Skills
             * @default []
             */
            skills: string[];
        };
        /**
         * CharacterUpdate
         * @description 캐릭터를 정할 때 받는 값. 보낸 것으로 캐릭터를 통째로 바꾼다.
         *
         *     방식(mode)에 따라 적는 칸이 다르다.
         *       - pregen: pregen_index 를 적는다. 이름이나 설명을 함께 보내면 그 칸은 보낸 것으로 고쳐 쓴다.
         *       - custom: 이름을 적는다. 숫자는 시나리오의 기본 시트를 받는다.
         *       - manual: 이름과 능력치의 점수(abilities)를 적는다. 최대 HP 는 적지 않는다. 규칙으로 구한다.
         *       - point_buy: manual 과 같은 칸을 적는다. 점수는 규칙의 총점 안에서 살 수 있는 것이어야 한다.
         *       - rolled: manual 과 같은 칸을 적는다. 점수는 먼저 굴려 둔 것을 남김없이 한 번씩 쓴 것이어야 한다.
         *         굴리는 것은 다른 주소다(POST .../character/roll). 굴린 점수를 여기에 적어 보내는 것이 아니다.
         *
         *     진행 중에 새 캐릭터를 들일 때도 같은 값을 받는다(POST .../character). 방식마다 적는 칸은 같다.
         *
         *     mode 를 비우면 pregen_index 가 있으면 pregen, 없으면 custom 으로 본다.
         *     능력치를 적는 방식은 여럿이라, 능력치를 보낼 때는 mode 를 반드시 적는다.
         */
        CharacterUpdate: {
            /** Abilities */
            abilities?: {
                [key: string]: number;
            } | null;
            /** Description */
            description?: string | null;
            mode?: components["schemas"]["CharacterMode"] | null;
            /** Name */
            name?: string | null;
            /** Pregen Index */
            pregen_index?: number | null;
        };
        /**
         * ChargeOut
         * @description 라운드의 서술 값을 내는 사람 하나의 청구(app/billing/charges.py).
         *
         *     status 는 청구의 상태다(pending, held, short, failed, capture_due, captured, release_due, released).
         *     credits 는 결제 서버가 실제로 홀드한 값이다. 아직 걸지 못했거나 결제 서버 없이 도는 서버면 null 이다.
         */
        ChargeOut: {
            /** Credits */
            credits: string | null;
            /** Status */
            status: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * CheckAction
         * @description 판정을 하는 행동.
         */
        CheckAction: {
            /** Ability */
            ability: string;
            /** Aim */
            aim?: string | null;
            /** Difficulty */
            difficulty?: string | null;
            /** Harm */
            harm?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "check";
            /**
             * Lethal
             * @default false
             */
            lethal: boolean;
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
            /** Recover */
            recover?: string | null;
            /** Risk */
            risk?: string | null;
            /** Strike */
            strike?: string | null;
            /** Target */
            target?: string | null;
            /** Weapon */
            weapon?: string | null;
        };
        /**
         * CheckOutcome
         * @description 판정의 결과. 엔진이 정한 것이다(app/engine/check.py 의 Check). 받는 값이 아니라 내보내는 값이다.
         */
        CheckOutcome: {
            blow?: components["schemas"]["BlowOut"] | null;
            called_shot?: components["schemas"]["CalledShotOut"] | null;
            drop?: components["schemas"]["DropOut"] | null;
            effect?: components["schemas"]["EffectOut"] | null;
            hindrance?: components["schemas"]["HindranceOut"] | null;
            item_throw?: components["schemas"]["app__rounds__schemas__ItemThrowOut"] | null;
            item_use?: components["schemas"]["ItemUseOut"] | null;
            /** Modifier */
            modifier: number;
            monster_effect?: components["schemas"]["MonsterEffectOut"] | null;
            npc_effect?: components["schemas"]["NpcEffectOut"] | null;
            /** Roll */
            roll: number;
            skill_use?: components["schemas"]["SkillUseOut"] | null;
            /** Success */
            success: boolean;
            /** Target */
            target: number;
            /** Total */
            total: number;
            treatment?: components["schemas"]["TreatmentOut"] | null;
            wake?: components["schemas"]["WakeOut"] | null;
        };
        /**
         * Clock
         * @description 게임 안의 시계. 테이블이 시작할 때의 시각(며칠째, 몇 시)과 라운드 하나에 흐르는 기본 시간(분).
         *
         *     시각은 1일째 0시부터 센다. 달 이름 같은 달력은 아직 없다. 셋을 함께 보낸다.
         *     라운드 하나에 흐르는 시간은 방장이 라운드마다 바꿀 수 있다. 여기 적는 것은 바꾸지 않았을 때의 값이다.
         */
        Clock: {
            /** Round Minutes */
            round_minutes: number;
            /** Start Day */
            start_day: number;
            /** Start Hour */
            start_hour: number;
        };
        /**
         * ClockOut
         * @description 테이블의 지금 시각과 다음 라운드에 흐를 시간.
         *
         *     next_step_minutes 는 실제로 흐를 시간이다. step_changed 가 참이면 엔진이 판의 기본보다 늘렸다
         *     (이번 라운드에 길을 갔거나 쉬었거나 모두 기다렸다). 라운드가 닫힌 뒤 다음 라운드가 열릴 때까지만 참일 수 있다.
         */
        ClockOut: {
            /** Day */
            day: number;
            /** Default Step Minutes */
            default_step_minutes: number;
            /** Hour */
            hour: number;
            /** Minute */
            minute: number;
            /** Next Step Minutes */
            next_step_minutes: number;
            /** Step Changed */
            step_changed: boolean;
            time_of_day: components["schemas"]["TimeOfDay"];
        };
        /**
         * ClockSnapshot
         * @description 게임 안의 시계. 테이블이 시작할 때의 시각(며칠째, 몇 시)과 라운드 하나에 흐르는 기본 시간(분).
         *
         *     비우면 새 시나리오의 기본값(1일째 8시, 10분)이다. 형식 24 보다 옛 판은 올릴 때 이 값을 적는다(upgrades.py).
         */
        ClockSnapshot: {
            /**
             * Round Minutes
             * @default 10
             */
            round_minutes: number;
            /**
             * Start Day
             * @default 1
             */
            start_day: number;
            /**
             * Start Hour
             * @default 8
             */
            start_hour: number;
        };
        /**
         * ClockTimeOut
         * @description 게임 안의 한 시각. 며칠째(1 부터), 몇 시, 몇 분, 하루의 어느 때.
         */
        ClockTimeOut: {
            /** Day */
            day: number;
            /** Hour */
            hour: number;
            /** Minute */
            minute: number;
            time_of_day: components["schemas"]["TimeOfDay"];
        };
        /**
         * CopiedFrom
         * @description 복사한 줄의 출처. 응답에 싣는다. 화면이 출처 표시(SRD 는 CC BY 4.0)를 한다.
         */
        CopiedFrom: {
            /** Key */
            key: string;
            /** Source */
            source: string;
        };
        /**
         * CoverAction
         * @description 지금 서 있는 장소의 숨을 곳에 엄폐하는 행동(app/rounds/covers.py, #276 의 커버 세이브). 받는 값이 없다.
         *
         *     그 라운드 동안 그 장소의 커버로 커버 세이브를 받는다. 차례를 기다리지 않는다. 숨는 것은 공격에 앞선다.
         *     그 라운드의 행동을 쓰므로 공격하지 못한다. 그것이 대가다.
         *     세이브 방식의 룰북에서, 커버가 있는 장소에 서 있을 때만 받는다. 서술이 "벽 뒤에 숨었다"고 써도 엄폐가 아니다.
         */
        CoverAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "cover";
        };
        /**
         * CoverOut
         * @description 엄폐한 결과(#276 의 커버 세이브). 엔진이 정했다(app/rounds/covers.py). 굴림이 없다.
         *
         *     place 는 숨은 장소, value 는 그 장소의 커버다. 그 라운드 동안 맞힌 공격에 이 값으로 커버 세이브를 굴렸다
         *     (판정의 blow.save, 몬스터·인물의 차례의 blow.save 의 kind 가 cover). 0 이면 커버가 없는 곳이라 숨지 못했다.
         */
        CoverOut: {
            place: components["schemas"]["PlaceRefOut"] | null;
            /** Value */
            value: number;
        };
        /**
         * CoverOutcome
         * @description 엄폐하는 행동의 결과.
         */
        CoverOutcome: {
            cover: components["schemas"]["CoverOut"];
        };
        /**
         * CoverRule
         * @description 장소 하나의 커버(#276 의 커버 세이브). 그 장소(place_id)에 숨을 곳이 얼마나 좋은지(cover, 1~10)다.
         *
         *     그 장소에서 엄폐한(cover 행동) 앉은 사람은 그 라운드에 이 값으로 커버 세이브를 받는다(app/rounds/covers.py).
         *     세이브 방식의 룰북에서만 쓰인다. 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "CoverRule-Input": {
            /** Cover */
            cover: number;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * CoverRule
         * @description 장소 하나의 커버(#276 의 커버 세이브). 그 장소(place_id)에 숨을 곳이 얼마나 좋은지(cover, 1~10)다.
         *
         *     그 장소에서 엄폐한(cover 행동) 앉은 사람은 그 라운드에 이 값으로 커버 세이브를 받는다(app/rounds/covers.py).
         *     세이브 방식의 룰북에서만 쓰인다. 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "CoverRule-Output": {
            /** Cover */
            cover: number;
            /** Place Id */
            place_id: string;
        };
        /**
         * CoverSnapshot
         * @description 장소 하나의 커버. 판 안의 장소 항목 하나(place_id)에 숨을 곳이 얼마나 좋은지(cover)다.
         */
        CoverSnapshot: {
            /** Cover */
            cover: number;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * CreditWaitUpdate
         * @description 크레딧이 모자란 사람을 기다리는 규칙을 바꿀 때 받는 값. 둘 다 적는다. 칸을 빼먹으면 거부한다.
         */
        CreditWaitUpdate: {
            /** Credit Wait Seconds */
            credit_wait_seconds: number;
            /** Remove Short Payers */
            remove_short_payers: boolean;
        };
        /**
         * CrossCheck
         * @description 길을 넘는 판정(#281). 절벽 오르기, 급류 헤엄치기처럼 지날 때마다 가는 사람이 굴린다.
         *
         *     ability 와 difficulty 는 찾는 판정(FindCheck)과 같다. 실패하면 가지 못하고 그 자리에 남는다.
         *     harm 을 적었으면 실패한 사람이 그 양의 등급(룰북의 magnitudes 의 이름)만큼 다친다(떨어짐, 휩쓸림).
         *     셋 다 룰북의 규칙에 있는지는 게시할 때 본다.
         */
        CrossCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /** Harm */
            harm?: string | null;
        };
        /**
         * CrossOut
         * @description 판에 적힌 판정 하나(#281). 길을 넘을 때, 자물쇠를 딸 때, 문을 부술 때다.
         *
         *     판에 적힌 능력과 난이도로 엔진이 굴렸다. 굴림은 공개다.
         */
        CrossOut: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string;
            hindrance?: components["schemas"]["HindranceOut"] | null;
            /** Modifier */
            modifier: number;
            /** Roll */
            roll: number;
            /** Success */
            success: boolean;
            /** Target */
            target: number;
            /** Total */
            total: number;
        };
        /**
         * CrossSnapshot
         * @description 길을 넘는 판정(#281). 판 안의 룰북의 능력치, 난이도, 실패했을 때 다치는 양의 등급의 이름이다.
         */
        CrossSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /** Harm */
            harm?: string | null;
        };
        /**
         * CureEffect
         * @description 적은 부상들(injuries)을 푼다. 대상이 입고 있지 않으면 아무 일도 없다.
         */
        CureEffect: {
            /** Injuries */
            injuries: string[];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "cure";
        };
        /**
         * CuredOut
         * @description 소모품이 푼 부상 하나(#277). 룰북의 부상의 이름표와 이름이다. 나으면서 생긴 후유증은 이벤트에 있다.
         */
        CuredOut: {
            /** Injury */
            injury: string;
            /** Name */
            name: string;
        };
        /**
         * Currency
         * @description 시나리오의 화폐(#278). 이름(금화)과 단위(닢), 캐릭터 모두가 시작할 때 받는 돈, 상인이 사 주는 값의 백분율이다.
         *
         *     결제의 크레딧과 상관없다. 게임 안의 돈이고 엔진만 바꾼다. 서술(AI)은 돈을 주거나 빼앗지 못한다.
         *     sell_percent 는 상인이 물건을 사 줄 때 물건의 값에 곱한다(내림). 0 이면 상인이 사 주지 않는다.
         */
        Currency: {
            /** Name */
            name: string;
            /**
             * Sell Percent
             * @default 50
             */
            sell_percent: number;
            /**
             * Starting
             * @default 0
             */
            starting: number;
            /**
             * Unit
             * @default
             */
            unit: string;
        };
        /**
         * CurrencyOut
         * @description 테이블의 화폐(#278). 판에 굳은 것이다. 돈은 엔진만 바꾼다. 결제의 크레딧과 상관없다.
         *
         *     sell_percent 는 상인이 사 주는 값의 백분율이다. 물건 하나의 값에 곱해 내림한다.
         */
        CurrencyOut: {
            /** Name */
            name: string;
            /** Sell Percent */
            sell_percent: number;
            /** Unit */
            unit: string;
        };
        /**
         * CurrencySnapshot
         * @description 화폐(#278). 이름과 단위, 캐릭터 모두가 시작할 때 받는 돈, 상인이 사 주는 값의 백분율이다.
         */
        CurrencySnapshot: {
            /** Name */
            name: string;
            /** Sell Percent */
            sell_percent: number;
            /**
             * Starting
             * @default 0
             */
            starting: number;
            /**
             * Unit
             * @default
             */
            unit: string;
        };
        /**
         * DamageEffect
         * @description 등급(magnitude)만큼 피해를 준다.
         *
         *     성질(nature, 룰북의 natures 의 이름표) 하나를 달 수 있다(#886 ③, 화염병). 맞는 쪽이 그 성질에 저항하면 반(내림),
         *     면역이면 0, 약점이면 두 배를 받는다. 비우면 누구나 그대로 받는다.
         */
        DamageEffect: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "damage";
            /** Magnitude */
            magnitude: string;
            /** Nature */
            nature?: string | null;
        };
        /**
         * DamageNatureOut
         * @description 피해의 성질(#886 ③)과 맞은 쪽이 받은 단계. 엔진이 정했다.
         *
         *     level 이 resist 면 방어구가 깎은 뒤의 양의 반(내림), immune 이면 0, vulnerable 이면 두 배를 받았다(amount 에
         *     이미 들었다). None 이면 그대로 받았다.
         */
        DamageNatureOut: {
            /** Key */
            key: string;
            level?: components["schemas"]["ResistLevel"] | null;
            /** Name */
            name: string;
        };
        /**
         * DeathSave
         * @description 죽음의 굴림. 쓰러진 캐릭터가 죽는지를 주사위가 정하는 법이다.
         *
         *     쓰러진 채로 라운드가 닫힐 때마다 규칙의 주사위(Ruleset.die)를 한 번 굴린다. 능력치의 보정은 더하지 않는다.
         *     눈이 target 이상이면 성공, 아니면 실패다. 성공과 실패를 따로 센다.
         *       - 실패가 failures 번 모이면 죽는다.
         *       - 성공이 successes 번 모이면 고비를 넘긴다. 더 굴리지 않는다. 쓰러진 채로 있고, 회복을 받으면 일어난다.
         *     회복을 받아 일어나면 센 것은 처음으로 돌아간다.
         */
        DeathSave: {
            /** Failures */
            failures: number;
            /** Successes */
            successes: number;
            /** Target */
            target: number;
        };
        /**
         * DeathSaveOut
         * @description 죽음의 굴림 한 번. 엔진이 굴린 것이다(app/engine/death.py 의 DeathSaveRoll).
         */
        DeathSaveOut: {
            /** Character Name */
            character_name: string;
            /** Failures */
            failures: number;
            fate: components["schemas"]["Fate"];
            /** Roll */
            roll: number;
            /** Success */
            success: boolean;
            /** Successes */
            successes: number;
            /** Target */
            target: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * DeclarationOut
         * @description 선언 하나.
         */
        DeclarationOut: {
            /** Action */
            action: (components["schemas"]["CheckAction"] | components["schemas"]["TreatAction"] | components["schemas"]["NameAction"] | components["schemas"]["UseAction"] | components["schemas"]["GiveAction"] | components["schemas"]["MoveAction"] | components["schemas"]["SearchAction"] | components["schemas"]["RestAction"] | components["schemas"]["TakeAction"] | components["schemas"]["PutDownAction"] | components["schemas"]["StealAction"] | components["schemas"]["LootAction"] | components["schemas"]["WaitAction"] | components["schemas"]["BuyAction"] | components["schemas"]["SellAction"] | components["schemas"]["PayAction"] | components["schemas"]["CoverAction"] | components["schemas"]["LockAction"] | components["schemas"]["UnlockAction"] | components["schemas"]["PickAction"] | components["schemas"]["ForceAction"] | components["schemas"]["RepairAction"] | components["schemas"]["ReplaceAction"] | components["schemas"]["ThrowAction"] | components["schemas"]["SkillAction"] | components["schemas"]["SetTrapAction"] | components["schemas"]["DisarmAction"]) | null;
            /** Character Name */
            character_name: string;
            /** Content */
            content: string | null;
            /** Outcome */
            outcome: components["schemas"]["CheckOutcome"] | components["schemas"]["NamingOutcome"] | components["schemas"]["ItemUseOutcome"] | components["schemas"]["SkillUseOutcome"] | components["schemas"]["ItemThrowOutcome"] | components["schemas"]["ItemGiveOutcome"] | components["schemas"]["MoveOutcome"] | components["schemas"]["SearchOutcome"] | components["schemas"]["DoorOutcome"] | components["schemas"]["TakeOutcome"] | components["schemas"]["PutDownOutcome"] | components["schemas"]["TrapSetOutcome"] | components["schemas"]["DisarmOutcome"] | components["schemas"]["StealOutcome"] | components["schemas"]["LootOutcome"] | components["schemas"]["RestOutcome"] | components["schemas"]["WaitOutcome"] | components["schemas"]["TradeOutcome"] | components["schemas"]["PayOutcome"] | components["schemas"]["CoverOutcome"] | components["schemas"]["TargetGoneOutcome"] | components["schemas"]["TurnLostOutcome"] | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * DeclarationUpdate
         * @description 선언을 낼 때 받는 값. 다시 내면 앞의 것을 통째로 바꾼다. 행동을 빼고 다시 내면 행동도 없어진다.
         *
         *     행동은 하나만 붙인다. 한 사람이 한 라운드에 주사위를 한 번 굴린다.
         *     행동은 판정(check), 치료(treat), 지목(name), 물건 쓰기(use), 건네기(give)다. 행동이 없으면 판정이 없는 선언이다.
         */
        DeclarationUpdate: {
            /** Action */
            action?: (components["schemas"]["CheckAction"] | components["schemas"]["TreatAction"] | components["schemas"]["NameAction"] | components["schemas"]["UseAction"] | components["schemas"]["GiveAction"] | components["schemas"]["MoveAction"] | components["schemas"]["SearchAction"] | components["schemas"]["RestAction"] | components["schemas"]["TakeAction"] | components["schemas"]["PutDownAction"] | components["schemas"]["StealAction"] | components["schemas"]["LootAction"] | components["schemas"]["WaitAction"] | components["schemas"]["BuyAction"] | components["schemas"]["SellAction"] | components["schemas"]["PayAction"] | components["schemas"]["CoverAction"] | components["schemas"]["LockAction"] | components["schemas"]["UnlockAction"] | components["schemas"]["PickAction"] | components["schemas"]["ForceAction"] | components["schemas"]["RepairAction"] | components["schemas"]["ReplaceAction"] | components["schemas"]["ThrowAction"] | components["schemas"]["SkillAction"] | components["schemas"]["SetTrapAction"] | components["schemas"]["DisarmAction"]) | null;
            /** Content */
            content: string;
        };
        /**
         * DepartureKind
         * @description 앉았던 사람이 자리를 떠난 길.
         * @enum {string}
         */
        DepartureKind: "left" | "kicked" | "dropped";
        /**
         * Difficulty
         * @description 난이도 한 단계. 예: 보통(15).
         */
        Difficulty: {
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Target */
            target: number;
        };
        /**
         * DisarmAction
         * @description 지금 서 있는 장소의 찾아낸 덫(trap) 하나를 해제하는 행동(#806 ①-b, app/rounds/trap_actions.py).
         *
         *     덫 물건에 적힌 해제 판정(능력, 난이도)으로 한 번 굴린다. 성공하면 덫을 거둬 그 물건을 갖는다.
         *     실패하면 덫은 그대로다. 목표보다 5 이상 모자라게 실패하면 덫이 해제하던 사람에게 터진다
         *     (피하는 판정 없이 효과가 든다).
         *     trap 은 테이블의 맵에 보이는 찾아낸 덫의 id(trap_id)다.
         */
        DisarmAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "disarm";
            /**
             * Trap
             * Format: uuid
             */
            trap: string;
        };
        /**
         * DisarmOut
         * @description 찾아낸 덫을 해제한 결과(#806 ①-b). 엔진이 정했다(app/rounds/trap_actions.py).
         *
         *     done 이 참이면 거뒀다. kept 는 그 덫 물건을 가진 개수다(0 이면 가득이라 그 장소에 보이게 두었다).
         *     실패하면 덫은 그대로다. 목표보다 5 이상 모자랐으면 덫이 터졌다(sprung). 그때 효과가 해제하던 사람에게 들었다
         *     (effect, injured, resources). 차례가 왔을 때 굴리지 못했으면 reason 이 있고(gone: 그 덫이 이미 끝났다,
         *     elsewhere: 그 덫의 장소에 없었다) check 는 None 이다.
         */
        DisarmOut: {
            /** Character Name */
            character_name: string;
            check: components["schemas"]["CrossOut"] | null;
            /** Done */
            done: boolean;
            effect?: components["schemas"]["EffectOut"] | null;
            /** Entry Id */
            entry_id: string | null;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /** Kept */
            kept: number;
            /** Name */
            name: string | null;
            place: components["schemas"]["PlaceRefOut"] | null;
            /** Reason */
            reason: string | null;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /** Sprung */
            sprung: boolean;
            /**
             * Trap Id
             * Format: uuid
             */
            trap_id: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * DisarmOutcome
         * @description 덫을 해제하는 행동의 결과.
         */
        DisarmOutcome: {
            disarm: components["schemas"]["DisarmOut"];
        };
        /**
         * DoorDevice
         * @description 문을 잠그는 장치(#281). 잠그기와 열기가 무엇으로 하는지다.
         * @enum {string}
         */
        DoorDevice: "lock" | "bar";
        /**
         * DoorOut
         * @description 길의 문을 다룬 결과(#281). 엔진이 정했다(app/rounds/door_actions.py).
         */
        DoorOut: {
            /** Act */
            act: string;
            aid?: components["schemas"]["AidOut"] | null;
            /** Character Name */
            character_name: string;
            check?: components["schemas"]["CrossOut"] | null;
            /** Device */
            device?: string | null;
            /** Done */
            done: boolean;
            from: components["schemas"]["PlaceRefOut"] | null;
            /** Reason */
            reason: string | null;
            to: components["schemas"]["PlaceRefOut"];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * DoorOutcome
         * @description 문을 다루는 행동의 결과(#281).
         */
        DoorOutcome: {
            door: components["schemas"]["DoorOut"];
        };
        /**
         * DropOut
         * @description 몬스터나 NPC 를 처음 쓰러뜨려 나온 물건들. 엔진이 굴리고 엔진이 줬다(app/rounds/drops.py).
         *
         *     source 가 monster 면 monster_id 와 monster_name 이, npc 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
         *     받는 사람은 그 장소(몬스터는 그 마리가 있던 곳, NPC 는 친 사람이 선 곳)의 죽지 않은 캐릭터 중
         *     서버의 주사위로 고른 한 명이다. 받을 사람이 없었으면 user_id 가 None 이고 나온 것은 모두 사라졌다(lost).
         */
        DropOut: {
            /** Character Name */
            character_name: string | null;
            /** Items */
            items: components["schemas"]["DroppedItemOut"][];
            /** Monster Id */
            monster_id?: string | null;
            /** Monster Name */
            monster_name?: string | null;
            /** Npc Id */
            npc_id?: string | null;
            /** Npc Name */
            npc_name?: string | null;
            /** Source */
            source: string;
            /** User Id */
            user_id: string | null;
        };
        /**
         * DroppedItemOut
         * @description 드롭으로 나온 물건 하나. 받은 개수, 한 가지의 상한을 넘어 잃은 개수, 받은 뒤의 개수다.
         */
        DroppedItemOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Lost */
            lost: number;
            /** Name */
            name: string;
            /** Total */
            total: number | null;
        };
        /**
         * DullKind
         * @description 훔치기가 쉬워지는 둔한 타입 하나. 대상의 타입(몬스터 도감의 kind)이 kind 이면 목표값이 amount 만큼 내려간다.
         */
        DullKind: {
            /** Amount */
            amount: number;
            /** Kind */
            kind: string;
        };
        /**
         * Effect
         * @description 부상의 효과 하나.
         *
         *     abilities 는 영향을 받는 능력이다. 비우면 모든 능력이다. 행동 불가에는 능력이 없다.
         *     amount 는 보정을 깎는 크기다. 보정 깎기에만 있다.
         */
        Effect: {
            /**
             * Abilities
             * @default []
             */
            abilities: string[];
            /**
             * Amount
             * @default 0
             */
            amount: number;
            kind: components["schemas"]["EffectKind"];
        };
        /**
         * EffectKind
         * @description 부상이 엔진에 주는 효과의 종류. 엔진이 실제로 집행하는 것은 이것뿐이다.
         *
         *     "그 손을 못 쓴다" 같은 것은 엔진이 알 수 없다. 행동에는 능력만 있고 몸의 부위는 없다.
         *     그런 것은 부상의 사실(Injury.fact)로 서술자에게 준다.
         * @enum {string}
         */
        EffectKind: "penalty" | "disadvantage" | "no_actions";
        /**
         * EffectOut
         * @description 판정의 결과로 HP 가 바뀐 것. 엔진이 정한 것이다.
         */
        EffectOut: {
            /** After */
            after: number;
            /** Amount */
            amount: number;
            /** Before */
            before: number;
            /** Character Name */
            character_name: string;
            /** Downed */
            downed: boolean;
            injury_roll?: components["schemas"]["InjuryRollOut"] | null;
            kind: components["schemas"]["ChangeKind"];
            /** Magnitude */
            magnitude: string;
            /** Max Hp */
            max_hp: number;
            nature?: components["schemas"]["DamageNatureOut"] | null;
            /**
             * Prank
             * @default false
             */
            prank: boolean;
            /** Rolls */
            rolls: number[];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * Encounter
         * @description 조우 하나. 맵의 장소 하나(place_id)에 몬스터 하나(monster_id)가 count 마리 있다.
         *
         *     장소가 붙인 로어북의 장소 항목인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
         *     로어북도 몬스터 시트도 나중에 바꿀 수 있어서 지금 정할 수 없다.
         */
        "Encounter-Input": {
            /** Count */
            count: number;
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
        };
        /**
         * Encounter
         * @description 조우 하나. 맵의 장소 하나(place_id)에 몬스터 하나(monster_id)가 count 마리 있다.
         *
         *     장소가 붙인 로어북의 장소 항목인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
         *     로어북도 몬스터 시트도 나중에 바꿀 수 있어서 지금 정할 수 없다.
         */
        "Encounter-Output": {
            /** Count */
            count: number;
            /** Monster Id */
            monster_id: string;
            /** Place Id */
            place_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
        };
        /**
         * EncounterSnapshot
         * @description 조우 하나. 판 안의 로어북 장소 항목 하나(place_id)에 판의 몬스터 하나(monster_id)가 count 마리 있다.
         */
        EncounterSnapshot: {
            /** Count */
            count: number;
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
        };
        /**
         * EntryCreate
         * @description 항목을 만들 때 받는 값. 이름만 필수다. 종류를 적지 않으면 기타다.
         *
         *     true_names 는 인물을 지목할 때 맞다고 받는 이름들이다. 비우면 항목의 이름 하나다. 인물 항목에만 뜻이 있다.
         */
        EntryCreate: {
            /**
             * Content
             * @default
             */
            content: string;
            /**
             * Keywords
             * @default []
             */
            keywords: string[];
            /** @default other */
            kind: components["schemas"]["LoreKind"];
            /** Name */
            name: string;
            /**
             * True Names
             * @default []
             */
            true_names: string[];
        };
        /**
         * EntryDetail
         * @description 항목 하나의 값.
         */
        EntryDetail: {
            /** Content */
            content: string;
            copied_from?: components["schemas"]["CopiedFrom"] | null;
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
            /** Keywords */
            keywords: string[];
            kind: components["schemas"]["LoreKind"];
            /** Name */
            name: string;
            /** True Names */
            true_names: string[];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * EntrySnapshot
         * @description 로어북의 항목 하나. 종류를 적지 않은 것(평가 데이터, 테스트)은 기타다.
         *
         *     true_names 는 인물을 지목할 때 맞다고 받는 이름들이다(app/rounds/naming.py). 비어 있으면 항목의 이름 하나다.
         *     적지 않은 것(평가 데이터, 테스트)은 비어 있다.
         */
        EntrySnapshot: {
            /** Content */
            content: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Keywords */
            keywords: string[];
            /** @default other */
            kind: components["schemas"]["LoreKind"];
            /** Name */
            name: string;
            /**
             * True Names
             * @default []
             */
            true_names: string[];
        };
        /**
         * EntryUpdate
         * @description 항목을 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     None 은 "보내지 않았다"는 뜻이다. 키워드를 전부 없애려면 빈 목록을 보낸다.
         */
        EntryUpdate: {
            /** Content */
            content?: string | null;
            /** Keywords */
            keywords?: string[] | null;
            kind?: components["schemas"]["LoreKind"] | null;
            /** Name */
            name?: string | null;
            /** True Names */
            true_names?: string[] | null;
        };
        /**
         * EquipmentSlot
         * @description 장비의 칸 하나(#276). 캐릭터가 물건을 착용하는 자리다. 예: 주손, 보조손, 몸.
         *
         *     칸마다 하나의 물건이 들어간다. 어느 물건이 어느 칸에 들어가는지는 시나리오의 아이템 규칙이 정한다.
         */
        EquipmentSlot: {
            /**
             * Hit Weight
             * @default 1
             */
            hit_weight: number;
            /** Key */
            key: string;
            /** Name */
            name: string;
        };
        /**
         * EventOut
         * @description 앉은 사람이 이벤트 하나를 볼 때의 값.
         */
        EventOut: {
            /**
             * Action Group Id
             * Format: uuid
             */
            action_group_id: string;
            /** Actor Id */
            actor_id: string | null;
            /** Caused By Sequence */
            caused_by_sequence: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Sequence */
            sequence: number;
            type: components["schemas"]["EventType"];
        };
        /**
         * EventPage
         * @description 이벤트 목록의 한 쪽.
         */
        EventPage: {
            /** Items */
            items: components["schemas"]["EventOut"][];
            /** Last Sequence */
            last_sequence: number;
        };
        /**
         * EventType
         * @description 이벤트의 종류. 지금 실제로 일어나는 일만 있다.
         *
         *     주사위, 판정, 상태 변경, AI 호출은 엔진과 AI 를 붙일 때 더한다.
         *
         *     DB 에는 CHECK 조건을 걸지 않는다. 종류는 계속 늘어나는데, 걸어 두면 늘릴 때마다 마이그레이션이 필요하다.
         *     이벤트를 적는 길은 하나뿐이고(app/events/recorder.py), 그 함수가 이 형식만 받는다.
         * @enum {string}
         */
        EventType: "table_created" | "member_joined" | "member_left" | "member_kicked" | "host_changed" | "abilities_rolled" | "reroll_granted" | "narration_style_changed" | "round_time_limit_changed" | "narration_tier_changed" | "narration_model_changed" | "credit_wait_changed" | "whisper_notice_changed" | "references_changed" | "friendly_fire_changed" | "friendly_fire_consent_changed" | "ledger_drafts_changed" | "whisper_sent" | "table_started" | "gm_narration" | "round_opened" | "player_action" | "check_rolled" | "hp_changed" | "npc_changed" | "npc_attitude_changed" | "monster_changed" | "monster_attacked" | "npc_attacked" | "injury_gained" | "injury_ended" | "injury_treated" | "naming_resolved" | "death_save_rolled" | "character_died" | "character_joined" | "items_gained" | "items_lost" | "item_used" | "skill_used" | "item_given" | "item_thrown" | "aid_used" | "item_put_down" | "trap_set" | "trap_sprung" | "trap_disarmed" | "equipment_changed" | "item_traded" | "money_paid" | "steal_attempted" | "quest_changed" | "clock_step_changed" | "character_moved" | "happening_occurred" | "place_searched" | "door_changed" | "monsters_appeared" | "character_rested" | "resource_changed" | "character_revived" | "round_closed" | "narration_failed" | "narration_abandoned" | "narration_credits_short" | "narration_model_not_for_sale" | "narration_model_retiring" | "narration_model_replaced" | "narration_model_unavailable" | "member_dropped" | "narration_credits_released" | "table_ended";
        /**
         * FallenOut
         * @description 떠난 캐릭터 하나. 죽었고, 그 플레이어가 새 캐릭터를 들였다. 숫자는 죽을 때의 것이다.
         */
        FallenOut: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            };
            /** Character Name */
            character_name: string;
            /** Max Hp */
            max_hp: number;
            /** Number */
            number: number;
            /** Pregen Index */
            pregen_index: number | null;
        };
        /**
         * Fate
         * @description 쓰러진 캐릭터의 갈림길.
         * @enum {string}
         */
        Fate: "dying" | "stable" | "dead";
        /**
         * FindCheck
         * @description 숨긴 길을 찾는 판정. 어느 능력치(ability)로, 어느 난이도(difficulty)로 굴리는가.
         *
         *     둘 다 룰북의 규칙에 있는 이름이다. 난이도를 적지 않으면 규칙의 기본 난이도다. 규칙에 있는지는 게시할 때 본다.
         */
        FindCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * FindSnapshot
         * @description 숨긴 길을 찾는 판정. 판 안의 룰북의 능력치와 난이도의 이름이다. 난이도가 없으면 규칙의 기본 난이도다.
         */
        FindSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * ForceAction
         * @description 지금 서 있는 장소에 닿은 길의 문을 부수는 행동(#281). 판에 적힌 부수는 판정(능력, 난이도)으로 굴린다.
         *
         *     성공하면 자물쇠와 빗장이 부서져 열린다. 부서진 문은 다시 잠그지 못한다. 지나가지는 않는다.
         *     부수기를 거드는 물건(item, 쇠지렛대)을 붙일 수 있다(#802).
         */
        ForceAction: {
            /** Item */
            item?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "force";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * ForceCheck
         * @description 문을 부수는 판정(#281). 행동 '부수기'가 이 능력과 난이도로 굴린다. 적지 않으면 부수지 못한다.
         *
         *     성공하면 자물쇠와 빗장이 부서져 열린다. 부서진 것은 고치기 전까지 다시 잠그거나 걸지 못한다.
         */
        ForceCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * ForceSnapshot
         * @description 문을 부수는 판정(#281). 능력치와 난이도의 이름이다.
         */
        ForceSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * FoundItemOut
         * @description 찾아서 가진 숨긴 물건 한 가지(app/rounds/place_item_actions.py). 찾은 사람이 바로 갖는다.
         */
        FoundItemOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Left */
            left: number;
            /** Name */
            name: string;
            /** Total */
            total: number;
        };
        /**
         * FoundRouteOut
         * @description 찾아낸 숨긴 길 하나. 두 끝과 양쪽으로 다니는지다.
         */
        FoundRouteOut: {
            from_place: components["schemas"]["PlaceRefOut"];
            to_place: components["schemas"]["PlaceRefOut"];
            /** Two Way */
            two_way: boolean;
        };
        /**
         * FoundTrapOut
         * @description 찾아낸 숨긴 덫 하나(#806 ①-b, app/rounds/trap_actions.py). 이제 테이블 모두가 알고, 캐릭터는 밟지 않는다.
         */
        FoundTrapOut: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            /**
             * Trap Id
             * Format: uuid
             */
            trap_id: string;
        };
        /**
         * FriendlyFire
         * @description 앉은 사람끼리 해칠 수 있는 정도(#803). 낮은 것부터 끔, 장난만, 다 됨이다.
         *
         *     테이블에 하나(방장이 정한다), 앉은 사람마다 하나(자기를 겨누는 것을 받아들이는 정도, 본인이 정한다) 있다.
         *     드는 것은 둘 중 낮은 것이다(app/tables/friendly_fire.py). 자기 자신에게 하는 것은 늘 된다.
         * @enum {string}
         */
        FriendlyFire: "off" | "prank" | "full";
        /**
         * FriendlyFireUpdate
         * @description 앉은 사람끼리 해칠 수 있는 정도를 바꿀 때 받는 값(#803). 칸을 빼먹으면 거부한다.
         *
         *     방장이 테이블의 것을 바꿀 때와, 앉은 사람이 자기를 겨누는 것을 받아들이는 정도를 바꿀 때 같은 모양이다.
         */
        FriendlyFireUpdate: {
            friendly_fire: components["schemas"]["FriendlyFire"];
        };
        /**
         * Genre
         * @description 장르. 운영자가 정한 목록에서 시나리오마다 하나를 고른다. 제작자가 자유롭게 적는 것은 태그다.
         *
         *     장르는 플레이 화면과 소개 화면의 테마를 정한다. 그래서 하나뿐이고, 이야기의 종류만 둔다.
         *     누구를 위한 이야기인가(남성향, 여성향)는 장르가 아니다. 태그로 적는다.
         *     목록을 바꾸려면 여기를 고쳐 배포한다. 값은 주소와 저장에 쓰는 이름이고, 화면에 보이는 말은 화면이 정한다.
         *     asset-server 의 캐릭터와 세계관도 같은 목록을 쓴다. 바꿀 때 함께 바꾼다.
         *     등급(성인용)은 장르가 아니다. 시나리오의 등급에서 온다.
         * @enum {string}
         */
        Genre: "fantasy" | "wuxia" | "urban_fantasy" | "sf" | "apocalypse" | "horror" | "mystery" | "romance" | "slice_of_life" | "alt_history" | "comedy";
        /**
         * GiveAction
         * @description 물건을 건네는 행동. 가진 물건 count 개를 앉은 다른 사람(target)에게 건넨다(app/rounds/item_actions.py).
         */
        GiveAction: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "give";
            /**
             * Target
             * Format: uuid
             */
            target: string;
        };
        /**
         * Grade
         * @description 보이는 분류. 목록을 묶어 보이는 데만 쓴다. 값은 모델마다 모델 목록의 파일에 적는다.
         * @enum {string}
         */
        Grade: "basic" | "standard" | "premium";
        /**
         * HappeningEffectKind
         * @description 사건이 일어났을 때 하는 일의 종류(#367). 효과는 목록이라 종류가 늘어도 판의 모양은 그대로다.
         * @enum {string}
         */
        HappeningEffectKind: "move" | "move_npc" | "lock_route" | "unlock_route" | "repair_route";
        /**
         * HappeningEffectSnapshot
         * @description 사건의 효과 하나. 캐릭터 옮기기(move), 인물 옮기기(move_npc, #282), 길의 문 다루기(#281)다.
         *     장소는 판의 맵의 장소 항목이다.
         *
         *     move: from_place 가 없으면 죽지 않은 캐릭터 모두를, 있으면 그 장소에 서 있던 죽지 않은 캐릭터만 to_place 로 옮긴다.
         *     move_npc: 판 안의 인물 항목 하나(npc)를 to_place 로 옮긴다. 죽은 인물은 옮기지 않는다. from_place 는 없다.
         *     lock_route, unlock_route, repair_route: 두 끝이 from_place 와 to_place 인 길(방향은 보지 않는다)의 문을
         *     잠그고, 열고, 고친다. 잠그고 열기는 device 의 장치만, 비었으면 그 문의 장치 모두다. 형식 54 보다 옛 판에는 없다.
         */
        HappeningEffectSnapshot: {
            device?: components["schemas"]["DoorDevice"] | null;
            /** From Place */
            from_place?: string | null;
            kind: components["schemas"]["HappeningEffectKind"];
            /** Npc */
            npc?: string | null;
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
        };
        /**
         * HappeningRule
         * @description 사건 규칙 하나(#367). 조건(when)이 채워지면 한 번 일어나 효과(effects)를 낸다. 붙인 로어북의 사건 항목 하나다.
         *
         *     조건의 모양과 종류는 퀘스트의 것과 같다(QuestCondition). 하나 이상 적는다.
         *     match 는 모두(all)인지 하나라도(any)인지다.
         *     가져가기(consume)는 쓰지 않는다. 사건은 물건을 받지 않는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)과
         *     물건을 잃는 조건(lose_item)도 쓸 수 있다. 같은 사건 항목이 퀘스트이기도 해도 된다(이름만 함께 쓴다).
         *     라운드가 닫힐 때 퀘스트를 본 뒤에 엔진이 본다. 일어난 것은 테이블에 적어 다시 일어나지 않는다
         *     (app/rounds/happenings.py).
         *     효과는 캐릭터 옮기기(MoveEffect)와 인물 옮기기(MoveNpcEffect, #282)다. kind 로 가른다.
         *     가리키는 사건과 장소, 옮기는 인물이 붙인 로어북에 있는지는 게시할 때 본다.
         */
        "HappeningRule-Input": {
            /** Effects */
            effects: (components["schemas"]["MoveEffect-Input"] | components["schemas"]["MoveNpcEffect-Input"] | components["schemas"]["RouteDoorEffect-Input"] | components["schemas"]["RepairRouteEffect-Input"])[];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /** When */
            when: components["schemas"]["QuestCondition-Input"][];
        };
        /**
         * HappeningRule
         * @description 사건 규칙 하나(#367). 조건(when)이 채워지면 한 번 일어나 효과(effects)를 낸다. 붙인 로어북의 사건 항목 하나다.
         *
         *     조건의 모양과 종류는 퀘스트의 것과 같다(QuestCondition). 하나 이상 적는다.
         *     match 는 모두(all)인지 하나라도(any)인지다.
         *     가져가기(consume)는 쓰지 않는다. 사건은 물건을 받지 않는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)과
         *     물건을 잃는 조건(lose_item)도 쓸 수 있다. 같은 사건 항목이 퀘스트이기도 해도 된다(이름만 함께 쓴다).
         *     라운드가 닫힐 때 퀘스트를 본 뒤에 엔진이 본다. 일어난 것은 테이블에 적어 다시 일어나지 않는다
         *     (app/rounds/happenings.py).
         *     효과는 캐릭터 옮기기(MoveEffect)와 인물 옮기기(MoveNpcEffect, #282)다. kind 로 가른다.
         *     가리키는 사건과 장소, 옮기는 인물이 붙인 로어북에 있는지는 게시할 때 본다.
         */
        "HappeningRule-Output": {
            /** Effects */
            effects: (components["schemas"]["MoveEffect-Output"] | components["schemas"]["MoveNpcEffect-Output"] | components["schemas"]["RouteDoorEffect-Output"] | components["schemas"]["RepairRouteEffect-Output"])[];
            /** Entry Id */
            entry_id: string;
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /** When */
            when: components["schemas"]["QuestCondition-Output"][];
        };
        /**
         * HappeningSnapshot
         * @description 사건 규칙 하나(#367). 판 안의 로어북 사건 항목 하나(entry_id)다. 조건(when)이 채워지면 한 번 일어나 효과를 낸다.
         *
         *     조건의 모양은 퀘스트의 것과 같다. match 는 그것을 모두 채워야 하는지 하나라도 되는지다.
         */
        HappeningSnapshot: {
            /** Effects */
            effects: components["schemas"]["HappeningEffectSnapshot"][];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /** When */
            when: components["schemas"]["QuestConditionSnapshot"][];
        };
        /**
         * HealEffect
         * @description HP 를 등급(magnitude)만큼 되돌린다.
         */
        HealEffect: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "heal";
            /** Magnitude */
            magnitude: string;
        };
        /**
         * Healing
         * @description 부상이 낫는 방식.
         * @enum {string}
         */
        Healing: "rounds" | "heals" | "permanent";
        /** HealthResponse */
        HealthResponse: {
            /** Status */
            status: string;
        };
        /**
         * HindranceOut
         * @description 입은 부상이 판정에 준 것. 보정을 깎았거나 불리하게 했다. 엔진이 정했다.
         */
        HindranceOut: {
            /** Disadvantage */
            disadvantage: boolean;
            /** Injuries */
            injuries: string[];
            /** Penalty */
            penalty: number;
            /** Rolls */
            rolls: number[];
        };
        /**
         * HostTransfer
         * @description 방장을 넘길 때 받는 값.
         */
        HostTransfer: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * InjureEffect
         * @description 부상 하나(injury)를 입힌다. 이미 입고 있으면 또 입히지 않는다.
         */
        InjureEffect: {
            /** Injury */
            injury: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "injure";
        };
        /**
         * InjuredOut
         * @description 소모품이 입힌 부상 하나(#800). 룰북의 부상의 이름표다.
         *
         *     이미 입고 있었으면 injury 가 None 이다. 몬스터가 그 성질에 면역이면 injury 는 None, immune 이 그 부상이다.
         *     동료의 장난(#803)이라 입히지 않은 오래 가는 부상이나 결손이면 injury 는 None, spared 가 그 부상이다.
         */
        InjuredOut: {
            /** Ends After Round */
            ends_after_round?: number | null;
            heals_at?: components["schemas"]["ClockTimeOut"] | null;
            /** Immune */
            immune?: string | null;
            /** Injury */
            injury: string | null;
            /** Spared */
            spared?: string | null;
        };
        /**
         * Injury
         * @description 부상 하나. 예: 팔 골절.
         *
         *     효과(effects)는 엔진이 판정에 적용하고, 사실(fact)은 서술자가 지킨다. 둘을 함께 적는다.
         *     rounds 는 짧은 것이 풀리기까지의 라운드 수다. 짧은 것에만 있다.
         *     heal_minutes 는 오래 가는 것이 저절로 낫기까지의 게임 안의 시간(분)이다. 오래 가는 것에만 있다.
         *     짧은 것은 "한 장면 동안"이라 라운드로, 오래 가는 것은 "며칠"이라 시간으로 센다(판 형식 25). 결손은 둘 다 없다.
         *     aftermath 는 오래 가는 것이 나을 때 굴리는 후유증 표다. 없으면 깨끗이 낫는다.
         *     aimable 은 노려 쳐서 일부러 입힐 수 있는 부상인가다.
         *     treat_difficulty 와 treat_minutes 는 치료다. 치료에 성공하면 나을 시각이 treat_minutes 만큼 앞당겨진다(#114 다).
         *     natures 는 부상의 성질이다(#799). 규칙의 성질(natures, #886)의 이름표다. 그 성질에 면역이면 이 부상을 입지 않는다.
         *     resistances 는 이 부상을 입고 있는 동안 생기는 저항이다(#886 ②).
         */
        Injury: {
            aftermath?: components["schemas"]["InjuryTable"] | null;
            /**
             * Aimable
             * @default false
             */
            aimable: boolean;
            /**
             * Effects
             * @default []
             */
            effects: components["schemas"]["Effect"][];
            /** Fact */
            fact: string;
            /** Heal Minutes */
            heal_minutes?: number | null;
            healing: components["schemas"]["Healing"];
            /** Key */
            key: string;
            /** Name */
            name: string;
            /**
             * Natures
             * @default []
             */
            natures: string[];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /** Rounds */
            rounds?: number | null;
            /** Treat Difficulty */
            treat_difficulty?: string | null;
            /** Treat Minutes */
            treat_minutes?: number | null;
        };
        /**
         * InjuryOut
         * @description 캐릭터가 입고 있는 부상 하나. 이름과 사실, 효과는 테이블의 rules.injuries 에서 이름표(injury)로 찾는다.
         */
        InjuryOut: {
            /** Ends After Round */
            ends_after_round: number | null;
            heals_at?: components["schemas"]["ClockTimeOut"] | null;
            /** Injury */
            injury: string;
            /** Round */
            round: number;
        };
        /**
         * InjuryRollOut
         * @description 부상이 생긴 일. 큰 타격이나 쓰러짐에 엔진이 부상 표를 굴렸거나, 노려 친 타격이 성공했거나,
         *     오래 가는 부상이 나을 때 후유증 표를 굴렸다.
         *
         *     injury 는 나온 부상의 이름표(규칙의 Injury.key)다. 부상이 없는 줄이면 None 이다.
         *     이름과 사실은 테이블의 rules 에 있다.
         */
        InjuryRollOut: {
            /** Ends After Round */
            ends_after_round: number | null;
            heals_at?: components["schemas"]["ClockTimeOut"] | null;
            /** Immune */
            immune?: string | null;
            /** Injury */
            injury: string | null;
            /** Roll */
            roll: number | null;
            /** Spared */
            spared?: string | null;
            /** Trigger */
            trigger: string;
        };
        /**
         * InjuryTable
         * @description 부상 표. sides 면 주사위를 한 번 굴려, 그 눈이 든 줄의 부상이 생긴다.
         *
         *     모든 눈이 정확히 한 줄에 든다. 줄은 낮은 눈부터 빈틈없이 이어진다. "부상 없음" 줄을 넉넉히 두면 자주 다치지 않는다.
         */
        InjuryTable: {
            /** Rows */
            rows: components["schemas"]["TableRow"][];
            /** Sides */
            sides: number;
        };
        /**
         * InjuryTriggers
         * @description 부상 표를 언제 굴리는가. 룰북이 골라 켜고 끈다.
         *
         *     big_hit_percent: 한 번의 피해(주사위가 정한 양)가 최대 HP 의 이 비율(%) 이상이면 굴린다. None 이면 끈다.
         *     downed: HP 가 0 이 되어 쓰러질 때 굴린다.
         *     called_shot: 노려 치기를 허용한다(#114 나).
         *     한 번의 피해에 여럿이 맞아도 한 번만 굴린다. 죽은 대상에게는 굴리지 않는다.
         */
        InjuryTriggers: {
            /** Big Hit Percent */
            big_hit_percent: number | null;
            /** Called Shot */
            called_shot: boolean;
            /** Downed */
            downed: boolean;
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
         * ItemAid
         * @description 물건이 행동 하나(act)를 거드는 방식. 판정에 bonus 를 더하고, 굴린 뒤 wear 대로 된다.
         */
        ItemAid: {
            act: components["schemas"]["AidAct"];
            /**
             * Bonus
             * @default 0
             */
            bonus: number;
            /** @default never */
            wear: components["schemas"]["AidWear"];
        };
        /**
         * ItemCheck
         * @description 물건을 인물이나 몬스터에게 쓸 때 맞히는 판정(#800). 어느 능력으로, 어느 난이도에 도전하는가.
         *
         *     물건을 자기와 동료에게 쓸 때는 굴리지 않는다. 인물(NPC)과 몬스터에게는 이로운 것이어도 늘 굴린다
         *     (잘못 먹이거나 엉뚱한 곳에 바를 수 있다). 맞히면 효과가 든다. 빗나가도 물건은 하나 없어진다.
         */
        ItemCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string;
        };
        /**
         * ItemGiveOut
         * @description 물건을 건넨 결과. 엔진이 정했다(app/rounds/item_actions.py).
         */
        ItemGiveOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Given */
            given: boolean;
            /** Name */
            name: string;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            target: components["schemas"]["ItemPersonOut"];
            /** Target Total */
            target_total: number | null;
        };
        /**
         * ItemGiveOutcome
         * @description 물건을 건네는 행동의 결과.
         */
        ItemGiveOutcome: {
            item_give: components["schemas"]["ItemGiveOut"];
        };
        /**
         * ItemKind
         * @description 아이템의 종류. 엔진이 다르게 다루는 것만 나눈다.
         *
         *     규칙을 적지 않은 물건 항목은 장비다. 갖고만 있고, 서술할 때 GM 에게 소지품으로 알려 준다.
         * @enum {string}
         */
        ItemKind: "gear" | "consumable";
        /**
         * ItemLock
         * @description 물건이 새 자물쇠일 때 그 자물쇠(#281). 행동 '바꾸기'로 판에 자물쇠가 있던 문에 단다.
         *
         *     단 자물쇠는 판의 자물쇠 대신 쓰인다. 여는 열쇠(key)는 새 것이다. 옛 열쇠로는 더 열지 못한다.
         *     열쇠는 붙인 로어북의 물건 항목 하나다. 길의 자물쇠의 열쇠, 다른 자물쇠 물건의 열쇠와 겹치지 못한다
         *     (게시의 route_key_repeated). 자물쇠 물건 자신을 열쇠로 적지 못한다.
         *     pick 을 적었으면 단 자물쇠를 따기로 열 수 있다. 적지 않으면 따지 못한다. 단 자물쇠는 열린 채다.
         *     한 테이블에서 자물쇠 물건 하나는 한 번만 단다. 달면 소지품에서 없어진다.
         */
        "ItemLock-Input": {
            /**
             * Key
             * Format: uuid
             */
            key: string;
            pick?: components["schemas"]["PickCheck"] | null;
        };
        /**
         * ItemLock
         * @description 물건이 새 자물쇠일 때 그 자물쇠(#281). 행동 '바꾸기'로 판에 자물쇠가 있던 문에 단다.
         *
         *     단 자물쇠는 판의 자물쇠 대신 쓰인다. 여는 열쇠(key)는 새 것이다. 옛 열쇠로는 더 열지 못한다.
         *     열쇠는 붙인 로어북의 물건 항목 하나다. 길의 자물쇠의 열쇠, 다른 자물쇠 물건의 열쇠와 겹치지 못한다
         *     (게시의 route_key_repeated). 자물쇠 물건 자신을 열쇠로 적지 못한다.
         *     pick 을 적었으면 단 자물쇠를 따기로 열 수 있다. 적지 않으면 따지 못한다. 단 자물쇠는 열린 채다.
         *     한 테이블에서 자물쇠 물건 하나는 한 번만 단다. 달면 소지품에서 없어진다.
         */
        "ItemLock-Output": {
            /** Key */
            key: string;
            pick?: components["schemas"]["PickCheck"] | null;
        };
        /**
         * ItemLockSnapshot
         * @description 물건이 문에 다는 새 자물쇠(#281). 여는 열쇠(판 안의 물건 항목)와 따는 판정(없으면 못 딴다).
         */
        ItemLockSnapshot: {
            /**
             * Key
             * Format: uuid
             */
            key: string;
            pick?: components["schemas"]["PickSnapshot"] | null;
        };
        /**
         * ItemOut
         * @description 캐릭터가 가진 물건 한 가지. 이름은 판의 로어북 물건 항목의 이름이다.
         *
         *     설명(항목의 글)은 싣지 않는다. 로어북은 AI 가 읽는 설정이라 비밀이 들어 있을 수 있다.
         */
        ItemOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            kind: components["schemas"]["ItemKind"];
            /** Name */
            name: string;
            rarity: components["schemas"]["ItemRarity"];
        };
        /**
         * ItemPersonOut
         * @description 물건을 받거나 회복받은 사람. 떠난 사람이면 캐릭터 이름이 없다.
         */
        ItemPersonOut: {
            /** Character Name */
            character_name: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * ItemRarity
         * @description 물건의 등급. 낮은 것부터 높은 것의 차례다. 규칙을 적지 않은 물건은 노말이다.
         *
         *     엔진은 등급이 높을수록 훔치기 어렵게 한다(#456). 값(가격)은 아직 없다. 사고팔기(#278)에서 더한다.
         * @enum {string}
         */
        ItemRarity: "normal" | "rare" | "unique" | "epic" | "legendary";
        /**
         * ItemRule
         * @description 아이템 규칙 하나. 붙인 로어북의 물건 항목 하나(entry_id)가 엔진에서 무엇인지 정한다.
         *
         *     규칙이 없는 물건 항목은 장비(gear)이고 노말이다. 소모품만 효과 목록(effects)을 적을 수 있다(#800).
         *     효과는 쓰면 대상에게 일어나는 일들이다(회복, 풀기, 피해, 부상, app/engine/item_effects.py). 차례대로 실행한다.
         *     등급과 부상이 룰북에 있는지는 게시할 때 본다. 예전의 heals(회복의 양)와 cures(푸는 부상)는 효과가 됐다.
         *     rarity 는 물건의 등급이다(노말, 레어, 유니크, 에픽, 레전드). 높을수록 훔치기 어렵다.
         *     price 는 상인이 파는 값이다(#278). 사 줄 때는 화폐의 백분율(currency.sell_percent)을 곱한다.
         *     비우면 사고팔 수 없는 물건이다. 화폐가 없는 시나리오에는 값을 적지 못한다(게시의 currency_missing).
         *     slots 는 착용할 때 들어갈 수 있는 룰북의 칸들, slot_count 는 그중 몇 칸을 함께 차지하는가다(#276).
         *     두 손 검은 주손과 보조손을 함께(2), 단검은 둘 중 하나(1)다. slots 를 비우면 착용하지 않는 물건이다.
         *     장비에만 적는다. 칸이 룰북에 있는지는 게시할 때 본다(item_slot_invalid).
         *     attack 은 무기의 공격 보정이다. 이 물건을 착용하고 공격할 때 판정에 더한다(#276).
         *     defense 는 차지한 칸(부위)의 방어, guard 는 모든 부위의 방어다(방패). 착용하면 공격을 막는다.
         *     어떻게 막는지는 룰북의 방어 규칙(armor.mode)이 정한다. 셋 다 착용하는 물건에만 적는다.
         *     ap 는 무기의 관통력이다. 관통하면 방어구로는 막지 못한다. ward 는 불굴 세이브의 값이다(부적, 역장).
         *     세이브 방식에서 관통을 무시하고 막는다. 여러 개를 착용하면 가장 큰 것을 쓴다.
         *     lock 은 이 물건이 문에 다는 새 자물쇠일 때의 그 자물쇠다(#281). 장비에만 적는다.
         *     throw 는 던지는 판정이다(#277). 장비에도 적을 수 있다(#801, 투척 도끼). 적지 않으면 룰북의 맞히는 판정으로 던진다.
         *     행동 '던지기'로 같은 장소의 몬스터나 인물에게 던지고, 맞으면 그 물건의 효과가 든다.
         *     aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py). 치료, 따기, 고치기, 부수기, 넘기에 붙여 쓰면
         *     판정에 보정을 더하고, 굴린 뒤 정한 대로 없어진다(늘, 실패하면, 안 없어짐). 장비와 소모품 모두 적는다.
         *     예전의 치료 보정(treat_bonus)은 치료의 거들기(늘 없어짐)가 됐다.
         *     resistances 는 착용하고 있는 동안 생기는 저항이다(#886 ②, 화염 저항의 망토). 착용하는 물건에만 적는다.
         *     nature 는 무기로 친 피해의 성질이다(#886 ③, 화염 검, 축복받은 망치). 무기에만 적는다.
         *     trap 은 이 물건이 덫일 때의 그 덫이다(#806, 곰덫, 독침 함정). 장비와 소모품 모두 적는다.
         *     성질이 룰북의 것인지는 게시할 때 본다(nature_invalid).
         */
        "ItemRule-Input": {
            /**
             * Aids
             * @default []
             */
            aids: components["schemas"]["ItemAid"][];
            /** Ap */
            ap?: number | null;
            /** Attack */
            attack?: number | null;
            /** Defense */
            defense?: number | null;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Guard */
            guard?: number | null;
            /** @default gear */
            kind: components["schemas"]["ItemKind"];
            lock?: components["schemas"]["ItemLock-Input"] | null;
            /** Nature */
            nature?: string | null;
            /** Price */
            price?: number | null;
            /** @default normal */
            rarity: components["schemas"]["ItemRarity"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Slot Count
             * @default 1
             */
            slot_count: number;
            /**
             * Slots
             * @default []
             */
            slots: string[];
            throw?: components["schemas"]["ItemThrow"] | null;
            trap?: components["schemas"]["ItemTrap"] | null;
            /** Ward */
            ward?: number | null;
        };
        /**
         * ItemRule
         * @description 아이템 규칙 하나. 붙인 로어북의 물건 항목 하나(entry_id)가 엔진에서 무엇인지 정한다.
         *
         *     규칙이 없는 물건 항목은 장비(gear)이고 노말이다. 소모품만 효과 목록(effects)을 적을 수 있다(#800).
         *     효과는 쓰면 대상에게 일어나는 일들이다(회복, 풀기, 피해, 부상, app/engine/item_effects.py). 차례대로 실행한다.
         *     등급과 부상이 룰북에 있는지는 게시할 때 본다. 예전의 heals(회복의 양)와 cures(푸는 부상)는 효과가 됐다.
         *     rarity 는 물건의 등급이다(노말, 레어, 유니크, 에픽, 레전드). 높을수록 훔치기 어렵다.
         *     price 는 상인이 파는 값이다(#278). 사 줄 때는 화폐의 백분율(currency.sell_percent)을 곱한다.
         *     비우면 사고팔 수 없는 물건이다. 화폐가 없는 시나리오에는 값을 적지 못한다(게시의 currency_missing).
         *     slots 는 착용할 때 들어갈 수 있는 룰북의 칸들, slot_count 는 그중 몇 칸을 함께 차지하는가다(#276).
         *     두 손 검은 주손과 보조손을 함께(2), 단검은 둘 중 하나(1)다. slots 를 비우면 착용하지 않는 물건이다.
         *     장비에만 적는다. 칸이 룰북에 있는지는 게시할 때 본다(item_slot_invalid).
         *     attack 은 무기의 공격 보정이다. 이 물건을 착용하고 공격할 때 판정에 더한다(#276).
         *     defense 는 차지한 칸(부위)의 방어, guard 는 모든 부위의 방어다(방패). 착용하면 공격을 막는다.
         *     어떻게 막는지는 룰북의 방어 규칙(armor.mode)이 정한다. 셋 다 착용하는 물건에만 적는다.
         *     ap 는 무기의 관통력이다. 관통하면 방어구로는 막지 못한다. ward 는 불굴 세이브의 값이다(부적, 역장).
         *     세이브 방식에서 관통을 무시하고 막는다. 여러 개를 착용하면 가장 큰 것을 쓴다.
         *     lock 은 이 물건이 문에 다는 새 자물쇠일 때의 그 자물쇠다(#281). 장비에만 적는다.
         *     throw 는 던지는 판정이다(#277). 장비에도 적을 수 있다(#801, 투척 도끼). 적지 않으면 룰북의 맞히는 판정으로 던진다.
         *     행동 '던지기'로 같은 장소의 몬스터나 인물에게 던지고, 맞으면 그 물건의 효과가 든다.
         *     aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py). 치료, 따기, 고치기, 부수기, 넘기에 붙여 쓰면
         *     판정에 보정을 더하고, 굴린 뒤 정한 대로 없어진다(늘, 실패하면, 안 없어짐). 장비와 소모품 모두 적는다.
         *     예전의 치료 보정(treat_bonus)은 치료의 거들기(늘 없어짐)가 됐다.
         *     resistances 는 착용하고 있는 동안 생기는 저항이다(#886 ②, 화염 저항의 망토). 착용하는 물건에만 적는다.
         *     nature 는 무기로 친 피해의 성질이다(#886 ③, 화염 검, 축복받은 망치). 무기에만 적는다.
         *     trap 은 이 물건이 덫일 때의 그 덫이다(#806, 곰덫, 독침 함정). 장비와 소모품 모두 적는다.
         *     성질이 룰북의 것인지는 게시할 때 본다(nature_invalid).
         */
        "ItemRule-Output": {
            /**
             * Aids
             * @default []
             */
            aids: components["schemas"]["ItemAid"][];
            /** Ap */
            ap?: number | null;
            /** Attack */
            attack?: number | null;
            /** Defense */
            defense?: number | null;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /** Entry Id */
            entry_id: string;
            /** Guard */
            guard?: number | null;
            /** @default gear */
            kind: components["schemas"]["ItemKind"];
            lock?: components["schemas"]["ItemLock-Output"] | null;
            /** Nature */
            nature?: string | null;
            /** Price */
            price?: number | null;
            /** @default normal */
            rarity: components["schemas"]["ItemRarity"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Slot Count
             * @default 1
             */
            slot_count: number;
            /**
             * Slots
             * @default []
             */
            slots: string[];
            throw?: components["schemas"]["ItemThrow"] | null;
            trap?: components["schemas"]["ItemTrap"] | null;
            /** Ward */
            ward?: number | null;
        };
        /**
         * ItemRuleSnapshot
         * @description 아이템 규칙 하나. 판 안의 로어북 물건 항목 하나(entry_id)가 엔진에서 무엇인지다.
         *
         *     effects 는 쓰면 대상에게 일어나는 일들이다(#800, app/engine/item_effects.py). 소모품에만 있다.
         *     rarity 는 물건의 등급이다.
         *     price 는 상인이 파는 값이다(#278). 비어 있으면 사고팔 수 없다.
         *     slots 는 착용할 때 들어갈 수 있는 규칙의 칸들, slot_count 는 그중 몇 칸을 함께 차지하는가다(#276).
         *     slots 가 비어 있으면 착용하지 않는 물건이다.
         *     lock 은 이 물건이 문에 다는 새 자물쇠일 때의 그 자물쇠다(#281).
         *     throw 는 던지는 판정이다(#277). aids 는 이 물건이 거드는 행동들이다(#802, app/engine/item_aids.py).
         */
        ItemRuleSnapshot: {
            /**
             * Aids
             * @default []
             */
            aids: components["schemas"]["ItemAid"][];
            /** Ap */
            ap?: number | null;
            /** Attack */
            attack?: number | null;
            /** Defense */
            defense?: number | null;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Guard */
            guard?: number | null;
            kind: components["schemas"]["ItemKind"];
            lock?: components["schemas"]["ItemLockSnapshot"] | null;
            /** Nature */
            nature?: string | null;
            /** Price */
            price?: number | null;
            /** @default normal */
            rarity: components["schemas"]["ItemRarity"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Slot Count
             * @default 1
             */
            slot_count: number;
            /**
             * Slots
             * @default []
             */
            slots: string[];
            throw?: components["schemas"]["ItemThrowSnapshot"] | null;
            trap?: components["schemas"]["ItemTrapSnapshot"] | null;
            /** Ward */
            ward?: number | null;
        };
        /**
         * ItemStack
         * @description 물건 몇 개. 붙인 로어북의 물건 항목 하나(entry_id)를 count 개다. 시작 소지품에 쓴다.
         *
         *     wear 는 그중 하나를 시작할 때 착용하는 칸들이다(#276). 비우면 착용하지 않고 시작한다.
         *     그 물건의 아이템 규칙이 정한 칸 중에서, 차지하는 칸의 수만큼 적는다. 퀘스트의 보상에는 적지 않는다.
         *     가리키는 항목이 붙인 로어북에 있는지, 물건인지, 칸이 맞는지는 게시할 때 본다. 로어북은 나중에 바꿀 수 있다.
         */
        "ItemStack-Input": {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * ItemStack
         * @description 물건 몇 개. 붙인 로어북의 물건 항목 하나(entry_id)를 count 개다. 시작 소지품에 쓴다.
         *
         *     wear 는 그중 하나를 시작할 때 착용하는 칸들이다(#276). 비우면 착용하지 않고 시작한다.
         *     그 물건의 아이템 규칙이 정한 칸 중에서, 차지하는 칸의 수만큼 적는다. 퀘스트의 보상에는 적지 않는다.
         *     가리키는 항목이 붙인 로어북에 있는지, 물건인지, 칸이 맞는지는 게시할 때 본다. 로어북은 나중에 바꿀 수 있다.
         */
        "ItemStack-Output": {
            /** Count */
            count: number;
            /** Entry Id */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * ItemStackSnapshot
         * @description 물건 몇 개. 판 안의 로어북 물건 항목 하나(entry_id)를 count 개다.
         *
         *     wear 는 그중 하나를 시작할 때 착용하는 규칙의 칸들이다(#276). 비어 있으면 착용하지 않는다.
         */
        ItemStackSnapshot: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Wear
             * @default []
             */
            wear: string[];
        };
        /**
         * ItemThrow
         * @description 물건을 던지는 판정(#277). 투척 단검처럼 던지기에 맞춘 물건에 적는다. 적지 않은 물건도 던질 수 있다(#801).
         *     그때는 룰북의 맞히는 판정(rules.item_check)으로 던진다.
         *
         *     ability 와 difficulty 는 룰북의 능력치와 난이도의 이름이다. 난이도를 비우면 룰북의 기본 난이도다.
         *     룰북의 규칙에 있는지는 게시할 때 본다(item_throw_invalid). 맞으면 그 물건의 효과(effects)가 든다.
         *     예전의 맞았을 때의 피해(harm)는 효과의 damage 가 됐다. 던지면 맞든 빗나가든 하나 없어진다.
         */
        ItemThrow: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * ItemThrowOutcome
         * @description 물건을 던지지 못한 결과(#277). 굴림이 없다. 겨눈 몬스터가 없어 못 던졌으면 그 까닭(target_gone)도 있다.
         */
        ItemThrowOutcome: {
            item_throw: components["schemas"]["app__rounds__schemas__ItemThrowOut"];
            target_gone?: components["schemas"]["TargetGoneOut"] | null;
        };
        /**
         * ItemThrowSnapshot
         * @description 물건을 던지는 판정(#277). 능력치와 난이도(없으면 룰북의 기본)다. 맞으면 물건의 효과가 든다(#801).
         */
        ItemThrowSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * ItemTrap
         * @description 덫(#806). 이 물건을 지금 장소에 숨겨 놓을 수 있다(행동 set_trap). 놓으면 소지품에서 하나 빠진다.
         *
         *     그 장소에 들어오는 쪽은 피하는 판정(avoid)을 굴린다. 실패하면 효과(effects)가 든다. 피하든 못 피하든 덫은 터진다.
         *     효과는 피해, 부상, 수치의 맞추기다(소모품의 효과와 같은 모양). 해제(disarm)는 찾은 덫을 거두는 판정이다.
         *     찾기(find)는 찾기 행동이 숨긴 덫을 찾는 판정이다(#806 ①-b). 비우면 피하는 판정과 같은 능력과 난이도로 굴린다.
         *     등급과 부상과 수치와 성질이 룰북에 있는지는 게시할 때 본다(item_trap_invalid).
         */
        ItemTrap: {
            avoid: components["schemas"]["TrapCheck"];
            disarm: components["schemas"]["TrapCheck"];
            /** Effects */
            effects: (components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            find?: components["schemas"]["TrapCheck"] | null;
        };
        /**
         * ItemTrapOut
         * @description 덫(#806). 행동 '덫 놓기'(set_trap)로 지금 장소에 숨겨 놓는다. 그 장소에 들어오는 쪽이 피하는 판정(avoid)을 굴리고,
         *     실패하면 효과(effects)가 든다. 해제(disarm)는 찾은 덫을 거두는 판정이다.
         *     찾기(find)는 찾기 행동이 숨긴 덫을 찾는 판정이다(#806 ①-b). 비었으면 피하는 판정으로 찾는다.
         */
        ItemTrapOut: {
            avoid: components["schemas"]["TrapCheckOut"];
            disarm: components["schemas"]["TrapCheckOut"];
            /** Effects */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            find?: components["schemas"]["TrapCheckOut"] | null;
        };
        /**
         * ItemTrapSnapshot
         * @description 덫(#806). 들어온 쪽이 피하는 판정, 찾은 덫을 거두는 해제 판정, 걸렸을 때의 효과들이다.
         *     찾기(find)는 숨긴 덫을 찾는 판정이다(#806 ①-b). 없으면 피하는 판정으로 찾는다.
         */
        ItemTrapSnapshot: {
            avoid: components["schemas"]["TrapCheckSnapshot"];
            disarm: components["schemas"]["TrapCheckSnapshot"];
            /** Effects */
            effects: (components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            find?: components["schemas"]["TrapCheckSnapshot"] | null;
        };
        /**
         * ItemUseOut
         * @description 물건을 쓴 결과. 엔진이 정했다(app/rounds/item_actions.py, item_targets.py).
         *
         *     자기와 동료에게는 굴리지 않는다. 인물과 몬스터에게 썼으면(#800) 맞히는 판정의 능력과 난이도가 있고,
         *     판정의 결과(CheckOutcome)에 이 문서가 붙는다.
         */
        ItemUseOut: {
            /** Ability */
            ability?: string | null;
            /**
             * Cured
             * @default []
             */
            cured: components["schemas"]["CuredOut"][];
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /** Name */
            name: string;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /** Target */
            target: components["schemas"]["ItemPersonOut"] | components["schemas"]["ThrownAtOut"] | null;
            /** Used */
            used: boolean;
        };
        /**
         * ItemUseOutcome
         * @description 물건을 쓰는 행동의 결과. 회복했으면 HP 의 변화(effect)가 함께 있다.
         */
        ItemUseOutcome: {
            effect?: components["schemas"]["EffectOut"] | null;
            item_use: components["schemas"]["ItemUseOut"];
            target_gone?: components["schemas"]["TargetGoneOut"] | null;
        };
        /**
         * JoinRequest
         * @description 초대 코드로 테이블에 들어갈 때 받는 값.
         */
        JoinRequest: {
            /** Invite Code */
            invite_code: string;
        };
        /**
         * KindImmunity
         * @description 몬스터의 타입 하나가 걸리지 않는 성질들(#886). 언데드는 독에, 구조물은 독과 정신에 걸리지 않는다.
         *
         *     예전에는 엔진에 박혀 있었다. 이제 룰북이 정한다. 몬스터의 시트가 더하거나(immune) 뺀다(vulnerable).
         */
        KindImmunity: {
            kind: components["schemas"]["MonsterKind"];
            /** Natures */
            natures: string[];
        };
        /**
         * KnownTrapOut
         * @description 찾아낸 덫 하나(#806 ①-b). 찾기 행동으로 찾으면 테이블 모두가 안다. 아는 덫은 캐릭터가 밟지 않는다.
         *     해제하기(disarm)로 거둔다. 이름은 덫 물건의 이름이다.
         */
        KnownTrapOut: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            /**
             * Trap Id
             * Format: uuid
             */
            trap_id: string;
        };
        /**
         * ListingDetail
         * @description 제작자가 자기 시나리오의 공개 정보를 볼 때의 값.
         */
        ListingDetail: {
            /** Description */
            description: string;
            genre: components["schemas"]["Genre"] | null;
            /** Published At */
            published_at: string | null;
            rating: components["schemas"]["Rating"] | null;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Tagline */
            tagline: string;
            /** Tags */
            tags: string[];
            /** Updated At */
            updated_at: string | null;
            /** Version */
            version: number | null;
        };
        /**
         * ListingPregen
         * @description 공개된 판의 프리젠 하나. 테이블을 만들기 전에 고를 거리를 보는 값이다. 함께 받는 소지품은 싣지 않는다.
         */
        ListingPregen: {
            /** Description */
            description: string;
            /** Name */
            name: string;
            sheet: components["schemas"]["CharacterSheet"];
        };
        /**
         * ListingUpdate
         * @description 소개 페이지를 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     None 은 "보내지 않았다"는 뜻이다. 태그를 전부 없애려면 빈 목록을 보낸다.
         *     장르는 반드시 하나다. 처음 쓸 때 함께 보내야 하고(없으면 409 genre_missing), 그 뒤에는 다른 것으로 바꿀 수만 있다.
         *     어느 판을 공개할지는 여기서 받지 않는다. 공개는 따로 하는 일이다(PublicationUpdate).
         */
        ListingUpdate: {
            /** Description */
            description?: string | null;
            genre?: components["schemas"]["Genre"] | null;
            /** Tagline */
            tagline?: string | null;
            /** Tags */
            tags?: string[] | null;
        };
        /**
         * LobbyJoinRequest
         * @description 로비에서 테이블에 들어갈 때 받는 값. 비밀번호가 걸린 테이블이면 비밀번호를 적는다.
         *
         *     길이를 검사하지 않는다(위쪽 끝만 막는다). 틀린 비밀번호는 모양이 어떻든 "틀렸다"로 답한다.
         */
        LobbyJoinRequest: {
            /** Password */
            password?: string | null;
        };
        /**
         * LockAction
         * @description 지금 서 있는 장소에 닿은 길(place 로 이어진 길)의 문을 잠그는 행동(#281, app/rounds/door_actions.py).
         *
         *     device 는 자물쇠(lock)인지 빗장(bar)인지다. 그 길에 하나만 있으면 비워도 된다. 둘 다 있으면 적어야 한다.
         *     자물쇠는 그 열쇠를 지녀야 잠그고, 빗장은 빗장 쪽에 서 있어야 건다. 부서진 문은 잠그지 못한다.
         */
        LockAction: {
            device?: components["schemas"]["DoorDevice"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "lock";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * LockSnapshot
         * @description 길의 자물쇠(#281). 여는 열쇠(판 안의 물건 항목), 시작할 때 잠겨 있는가, 따는 판정(없으면 못 딴다).
         */
        LockSnapshot: {
            /**
             * Key
             * Format: uuid
             */
            key: string;
            /**
             * Locked
             * @default true
             */
            locked: boolean;
            pick?: components["schemas"]["PickSnapshot"] | null;
        };
        /**
         * LongRest
         * @description 긴 휴식. minutes 분을 쉬면 최대 HP 까지 회복한다.
         */
        LongRest: {
            /** Minutes */
            minutes: number;
        };
        /**
         * LootAction
         * @description 쓰러졌거나 죽은 대상이 지닌 물건 하나(item)를 가져가는 행동(app/rounds/loots.py, #475).
         *
         *     대상은 같은 장소의 몬스터 한 마리(monster)나 이번 장면의 인물(npc)이다. 둘 중 하나만 적는다.
         *     판정이 없다. 그 줄을 통째로 갖는다. 살아 있는(쓰러지지 않은) 대상에게서는 가져가지 못한다. 그때는 훔치기다.
         */
        LootAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "loot";
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
        };
        /**
         * LootOut
         * @description 빼앗은 결과. 엔진이 정했다(app/rounds/loots.py). 판정이 없다.
         *
         *     대상이 몬스터면 monster_id 와 monster_name 이, NPC 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
         *     looted 가 참이면 가져갔다(count 는 가져간 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수).
         *     reason: gone(앞사람이 먼저 가져갔다), full(상한에 닿아 그만큼만, 또는 하나도), awake(대상이 깨어 있었다).
         */
        LootOut: {
            /** Character Name */
            character_name: string;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Left */
            left: number;
            /** Looted */
            looted: boolean;
            /** Monster Id */
            monster_id?: string | null;
            /** Monster Name */
            monster_name?: string | null;
            /** Name */
            name: string;
            /** Npc Id */
            npc_id?: string | null;
            /** Npc Name */
            npc_name?: string | null;
            /** Reason */
            reason: string | null;
            /** Total */
            total: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * LootOutcome
         * @description 빼앗는 행동의 결과.
         */
        LootOutcome: {
            loot: components["schemas"]["LootOut"];
        };
        /**
         * LoreCopyResult
         * @description 로어북으로 복사한 결과. skipped 는 이미 복사해 두어 건너뛴 줄의 id 다.
         */
        LoreCopyResult: {
            /** Created */
            created: components["schemas"]["EntryDetail"][];
            /** Skipped */
            skipped: string[];
        };
        /**
         * LoreKind
         * @description 로어북 항목의 종류. 시스템이 다르게 다루는 것만 나눈다. 더 촘촘한 분류는 나중에 자유 태그로 받는다.
         *
         *     종류마다 하는 일(app/lore/retrieval.py, app/rounds/prompt.py):
         *       - 인물: 이름이 장면에 아직 안 나왔으면 장면의 호칭으로 이름표를 바꾸고 진짜 이름을 뺀다
         *       - 전설: 사실로 단정하지 않고 흘릴 수 있는 이야기로 다룬다
         *       - 사건: 준비된 사건의 글이다. 장면에서 먼저 일으키거나 결말을 정하지 않는다.
         *               사건 하나가 퀘스트 하나다. 시작 상태와 보상은 시나리오의 퀘스트 규칙(Scenario.quests),
         *               진행(상태)은 테이블(엔진, DB)이 맡는다
         *     장소는 맵의 장소다. 어디와 어디가 이어지는지는 시나리오의 길(Scenario.routes)이 정한다.
         *     물건, 세력, 종족은 지금은 표시만 한다(물건은 시나리오의 아이템 규칙이 엔진에 잇는다).
         * @enum {string}
         */
        LoreKind: "person" | "place" | "item" | "faction" | "species" | "legend" | "event" | "other";
        /**
         * LorebookCreate
         * @description 로어북을 만들 때 받는 값. 공통 칸뿐이다. 항목은 만든 뒤에 하나씩 더한다.
         */
        LorebookCreate: {
            /**
             * Description
             * @default
             */
            description: string;
            /** Title */
            title: string;
        };
        /**
         * LorebookSnapshot
         * @description 로어북 하나와 그 항목 전부.
         */
        LorebookSnapshot: {
            /** Entries */
            entries: components["schemas"]["EntrySnapshot"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
        };
        /**
         * LorebookUpdate
         * @description 로어북을 고칠 때 받는 값. 공통 칸뿐이다.
         */
        LorebookUpdate: {
            /** Description */
            description?: string | null;
            /** Title */
            title?: string | null;
        };
        /**
         * Magnitude
         * @description 피해와 회복의 양을 나타내는 등급 하나. 예: 가벼움(1d4).
         *
         *     양은 주사위로 정한다. count 개의 sides 면 주사위를 굴려 더한다. count 2, sides 8 이면 2d8 이다.
         *     피해와 회복이 같은 등급을 쓴다. 가벼운 피해도 가벼운 회복도 1d4 다.
         */
        Magnitude: {
            /** Count */
            count: number;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Sides */
            sides: number;
        };
        /**
         * MapOut
         * @description 테이블이 아는 맵. 앉은 사람 모두가 같은 것을 본다. 방장도 마찬가지다.
         *
         *     숨긴 길과 숨긴 길로만 닿는 장소, 아직 서 보지 않은 안개 길은 싣지 않는다(app/tables/places.py).
         */
        MapOut: {
            /** Places */
            places: components["schemas"]["PlaceOut"][];
            /** Routes */
            routes: components["schemas"]["RouteOut"][];
        };
        /** MeResponse */
        MeResponse: {
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * MemberOut
         * @description 테이블에 앉은 사람 하나.
         */
        MemberOut: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            } | null;
            character: components["schemas"]["CharacterOut"] | null;
            character_mode: components["schemas"]["CharacterMode"] | null;
            /** Fallen */
            fallen: components["schemas"]["FallenOut"][];
            friendly_fire: components["schemas"]["FriendlyFire"];
            /** Is Host */
            is_host: boolean;
            /**
             * Joined At
             * Format: date-time
             */
            joined_at: string;
            /** Pregen Index */
            pregen_index: number | null;
            roll: components["schemas"]["RollOut"] | null;
            sheet: components["schemas"]["SheetOut"] | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * MessageCreate
         * @description 채팅을 쓸 때 받는 값. 누가 썼는지는 토큰에서 읽는다. 입력으로 받지 않는다.
         */
        MessageCreate: {
            /** Content */
            content: string;
        };
        /**
         * MessageOut
         * @description 앉은 사람이 채팅 한 줄을 볼 때의 값.
         */
        MessageOut: {
            /** Character Name */
            character_name: string | null;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Sequence */
            sequence: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * MessagePage
         * @description 채팅 목록의 한 쪽.
         */
        MessagePage: {
            /** Items */
            items: components["schemas"]["MessageOut"][];
            /** Last Sequence */
            last_sequence: number;
        };
        /**
         * Mishap
         * @description 치료에 실패했을 때 일어나는 일의 종류. 치료 실패 표의 한 줄이 이 중 하나다.
         * @enum {string}
         */
        Mishap: "nothing" | "pain" | "worsen" | "fatal";
        /**
         * MishapOut
         * @description 치료에 실패해 치료 실패 표를 굴린 것. 엔진이 굴렸다.
         */
        MishapOut: {
            /** Delay Minutes */
            delay_minutes?: number | null;
            /** Kind */
            kind: string;
            /** Magnitude */
            magnitude: string | null;
            /** Roll */
            roll: number;
        };
        /**
         * MishapRow
         * @description 치료 실패 표의 한 줄. 눈이 low 이상 high 이하면 이 줄이다.
         */
        MishapRow: {
            /** Delay Minutes */
            delay_minutes?: number | null;
            /** High */
            high: number;
            kind: components["schemas"]["Mishap"];
            /** Low */
            low: number;
            /** Magnitude */
            magnitude?: string | null;
        };
        /**
         * MishapTable
         * @description 치료 실패 표. 치료 판정에 실패하면 sides 면 주사위를 한 번 굴려, 그 눈이 든 줄의 일이 일어난다.
         */
        MishapTable: {
            /** Rows */
            rows: components["schemas"]["MishapRow"][];
            /** Sides */
            sides: number;
        };
        /**
         * ModelState
         * @description 작성자 화면에 보이는 추천 모델의 상태.
         * @enum {string}
         */
        ModelState: "ok" | "retiring" | "unavailable";
        /**
         * ModelStatusOut
         * @description 작성자 화면에 보이는 추천 서술 모델의 상태(app/assets/scenarios/recommended_model.py).
         *
         *     state 가 ok 가 아니면 화면이 작성자에게 알린다. replacement 는 지금 테이블을 만들면 대신 쓸 모델이다.
         *     가격 목록을 받지 못했거나 같은 회사에 대신할 모델이 없으면 null 이다. 그때는 방장이 모델을 고른다.
         */
        ModelStatusOut: {
            /** Replacement */
            replacement: string | null;
            /** Retires On */
            retires_on: string | null;
            state: components["schemas"]["ModelState"];
        };
        /**
         * Modifier
         * @description 능력치의 점수를 판정에 더하는 값(보정)으로 바꾸는 방법.
         *
         *     보정 = (점수 - base) // step. 내림한다.
         *     base 10, step 2 이면 점수 14 는 +2, 점수 9 는 -1 이다.
         *     base 0, step 1 이면 점수가 그대로 보정이다.
         */
        Modifier: {
            /** Base */
            base: number;
            /** Step */
            step: number;
        };
        /**
         * MonsterAttack
         * @description 몬스터의 공격(스킬) 하나. 몬스터의 차례에 이 능력치로 이 난이도에 판정하고, 맞으면 대상이 이 등급만큼 피해를 입는다.
         *     effects 가 있으면(#805 ③-b) 맞혔을 때 대상에게 그 효과들(부상, 수치의 맞추기)이 더 든다.
         *     방어와 세이브는 피해만 막는다.
         *     피해 등급(harm)은 비울 수 있다. 그때는 효과만 있는 공격이다(독 뿜기). 피해도 효과도 없는 공격은 받지 않는다.
         *
         *     이름표(능력치, 난이도, 양의 등급)는 룰북의 것이다. 규칙에 있는지는 게시할 때 본다(monster_attack_invalid).
         *     NPC 시트의 공격도 이 모양이다(#487). 그때 게시의 문제는 npc_attack_invalid 다.
         *     cost 는 쓸 때 내는 비용이다(#805 ③-a). 그 몬스터나 인물이 가진 수치(rules.resources 의 holders) 하나를 그만큼 낸다.
         *     비우면 공짜다. 차례에 이 공격을 골랐는데 모자라면 그 차례에 아무것도 하지 못한다. 빗나가도 낸다.
         *     nature 는 피해의 성질이다(#886 ③). 맞은 쪽의 저항(반), 면역(0), 약점(두 배)을 따른다. 비우면 무기의 성질이다.
         */
        "MonsterAttack-Input": {
            /** Ability */
            ability: string;
            cost?: components["schemas"]["SkillCost"] | null;
            /** Difficulty */
            difficulty: string;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /** Harm */
            harm?: string | null;
            /** Name */
            name: string;
            /** Nature */
            nature?: string | null;
            /** Weapon */
            weapon?: string | null;
        };
        /**
         * MonsterAttack
         * @description 몬스터의 공격(스킬) 하나. 몬스터의 차례에 이 능력치로 이 난이도에 판정하고, 맞으면 대상이 이 등급만큼 피해를 입는다.
         *     effects 가 있으면(#805 ③-b) 맞혔을 때 대상에게 그 효과들(부상, 수치의 맞추기)이 더 든다.
         *     방어와 세이브는 피해만 막는다.
         *     피해 등급(harm)은 비울 수 있다. 그때는 효과만 있는 공격이다(독 뿜기). 피해도 효과도 없는 공격은 받지 않는다.
         *
         *     이름표(능력치, 난이도, 양의 등급)는 룰북의 것이다. 규칙에 있는지는 게시할 때 본다(monster_attack_invalid).
         *     NPC 시트의 공격도 이 모양이다(#487). 그때 게시의 문제는 npc_attack_invalid 다.
         *     cost 는 쓸 때 내는 비용이다(#805 ③-a). 그 몬스터나 인물이 가진 수치(rules.resources 의 holders) 하나를 그만큼 낸다.
         *     비우면 공짜다. 차례에 이 공격을 골랐는데 모자라면 그 차례에 아무것도 하지 못한다. 빗나가도 낸다.
         *     nature 는 피해의 성질이다(#886 ③). 맞은 쪽의 저항(반), 면역(0), 약점(두 배)을 따른다. 비우면 무기의 성질이다.
         */
        "MonsterAttack-Output": {
            /** Ability */
            ability: string;
            cost?: components["schemas"]["SkillCost"] | null;
            /** Difficulty */
            difficulty: string;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /** Harm */
            harm?: string | null;
            /** Name */
            name: string;
            /** Nature */
            nature?: string | null;
            /** Weapon */
            weapon?: string | null;
        };
        /**
         * MonsterCopyResult
         * @description 도감으로 복사한 결과. skipped 는 이미 복사해 두어 건너뛴 줄의 id 다.
         */
        MonsterCopyResult: {
            /** Created */
            created: components["schemas"]["MonsterDetail"][];
            /** Skipped */
            skipped: string[];
        };
        /**
         * MonsterCreate
         * @description 몬스터를 만들 때 받는 값. 이름만 필수다. 타입을 적지 않으면 기타다.
         */
        MonsterCreate: {
            /**
             * Content
             * @default
             */
            content: string;
            /** @default other */
            kind: components["schemas"]["MonsterKind"];
            /** Name */
            name: string;
            /**
             * Unique
             * @default false
             */
            unique: boolean;
        };
        /**
         * MonsterDetail
         * @description 몬스터 하나의 값.
         */
        MonsterDetail: {
            /** Content */
            content: string;
            copied_from?: components["schemas"]["CopiedFrom"] | null;
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
            kind: components["schemas"]["MonsterKind"];
            /** Name */
            name: string;
            /** Unique */
            unique: boolean;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * MonsterEffectOut
         * @description 판정의 결과로 몬스터 한 마리의 상태가 바뀐 것. 엔진이 정한 것이다. 피해뿐이다.
         *
         *     NPC 와 같이 HP 의 숫자는 싣지 않는다. 주사위의 눈과 양, 바뀐 생사는 보인다.
         */
        MonsterEffectOut: {
            /** Amount */
            amount: number;
            injury_roll?: components["schemas"]["InjuryRollOut"] | null;
            kind: components["schemas"]["ChangeKind"];
            /** Lethal */
            lethal: boolean;
            /** Magnitude */
            magnitude: string;
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /** Name */
            name: string;
            nature?: components["schemas"]["DamageNatureOut"] | null;
            /** Rolls */
            rolls: number[];
            status: components["schemas"]["NpcStatus"];
        };
        /**
         * MonsterKind
         * @description 몬스터의 타입. 엔진이 다르게 다룰 것만 나눈다. 자유 태그로 두지 않는다. 서버가 타입마다 다르게 다룰 수 없게 된다.
         *
         *     타입마다 엔진이 하는 일(예: 언데드와 구조물에는 치료가 듣지 않는다)은 판정에 몬스터를 붙일 때 정한다.
         *     그때 값을 다시 본다. 지금은 값만 받는다. 세세한 생물 분류는 로어북의 종족 항목이 글로 맡는다.
         * @enum {string}
         */
        MonsterKind: "humanoid" | "beast" | "undead" | "construct" | "other";
        /**
         * MonsterSheet
         * @description 몬스터 시트 하나. 붙인 도감의 몬스터 하나(monster_id)에 숫자를 준다.
         *
         *     시트를 적은 몬스터만 이 시나리오가 쓴다. 판에는 시트가 있는 몬스터만 들어간다.
         *     가리키는 몬스터가 붙인 도감에 있는지, 시트가 규칙에 맞는지는 게시할 때 본다. NPC 시트와 같은 까닭이다.
         */
        "MonsterSheet-Input": {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["MonsterAttack-Input"][];
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItem-Input"][];
            /**
             * Immune
             * @default []
             */
            immune: string[];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItem-Input"][];
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /**
             * Natural Armor
             * @default []
             */
            natural_armor: components["schemas"]["NaturalArmor"][];
            /** Nature */
            nature?: string | null;
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
            /**
             * Vulnerable
             * @default []
             */
            vulnerable: string[];
            /** Ward */
            ward?: number | null;
        };
        /**
         * MonsterSheet
         * @description 몬스터 시트 하나. 붙인 도감의 몬스터 하나(monster_id)에 숫자를 준다.
         *
         *     시트를 적은 몬스터만 이 시나리오가 쓴다. 판에는 시트가 있는 몬스터만 들어간다.
         *     가리키는 몬스터가 붙인 도감에 있는지, 시트가 규칙에 맞는지는 게시할 때 본다. NPC 시트와 같은 까닭이다.
         */
        "MonsterSheet-Output": {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["MonsterAttack-Output"][];
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItem-Output"][];
            /**
             * Immune
             * @default []
             */
            immune: string[];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItem-Output"][];
            /** Monster Id */
            monster_id: string;
            /**
             * Natural Armor
             * @default []
             */
            natural_armor: components["schemas"]["NaturalArmor"][];
            /** Nature */
            nature?: string | null;
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
            /**
             * Vulnerable
             * @default []
             */
            vulnerable: string[];
            /** Ward */
            ward?: number | null;
        };
        /**
         * MonsterSheetProposal
         * @description 몬스터 시트의 제안. 저장하지 않는다. sheet 는 시나리오의 monster_sheets 에 그대로 넣을 수 있는 모양이다.
         *
         *     notes 는 원본과 다르게 옮긴 것들이다(범위에 맞춘 점수, 옮기지 않은 행동). 제작자가 읽고 고친다.
         *     copied_from 은 수치를 가져온 참고 자료다.
         */
        MonsterSheetProposal: {
            copied_from: components["schemas"]["CopiedFrom"];
            /** Notes */
            notes: string[];
            sheet: components["schemas"]["MonsterSheet-Output"];
        };
        /**
         * MonsterSnapshot
         * @description 몬스터 하나. 도감의 몬스터(글과 타입)와 시나리오의 몬스터 시트(숫자)를 합친 것이다.
         *
         *     한 종류다. 테이블에 몇 마리가 나오든 판에는 하나다. 어느 도감에서 왔는지는 플레이에 쓰지 않아서 싣지 않는다.
         */
        MonsterSnapshot: {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["AttackSnapshot"][];
            /** Content */
            content: string;
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItemSnapshot"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Immune
             * @default []
             */
            immune: string[];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItemSnapshot"][];
            kind: components["schemas"]["MonsterKind"];
            /** Name */
            name: string;
            /**
             * Natural Armor
             * @default []
             */
            natural_armor: components["schemas"]["NaturalArmorSnapshot"][];
            /** Nature */
            nature?: string | null;
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
            /**
             * Unique
             * @default false
             */
            unique: boolean;
            /**
             * Vulnerable
             * @default []
             */
            vulnerable: string[];
            /** Ward */
            ward?: number | null;
        };
        /**
         * MonsterUpdate
         * @description 몬스터를 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     None 은 "보내지 않았다"는 뜻이다. 내용을 비우려면 빈 문자열을 보낸다.
         */
        MonsterUpdate: {
            /** Content */
            content?: string | null;
            kind?: components["schemas"]["MonsterKind"] | null;
            /** Name */
            name?: string | null;
            /** Unique */
            unique?: boolean | null;
        };
        /**
         * MoveAction
         * @description 맵에서 한 칸 가는 행동. 지금 서 있는 장소에서 아는 길로 이어진 장소(place)로 간다(app/rounds/map_actions.py).
         *
         *     place 는 판의 로어북 장소 항목의 id 다. 엔진은 이 값을 읽지 않는다. 어디와 이어져 있는지는 판이 안다.
         *     한 라운드에 한 칸이다. 한 사람의 선언에는 행동이 하나다.
         *     carry 는 함께 업고 갈 쓰러진 동료(앉은 사람의 user_id)다. 한 사람이 한 명을 업는다(#367).
         *     item 은 길을 넘는 판정을 거드는 물건이다(#802, 밧줄). 넘는 판정이 있는 길에만 적는다.
         */
        MoveAction: {
            /** Carry */
            carry?: string | null;
            /** Item */
            item?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * MoveEffect
         * @description 사건의 효과 하나: 캐릭터들을 맵의 한 장소(to_place)로 옮긴다(#367).
         *
         *     from_place 가 없으면 죽지 않은 캐릭터 모두를, 있으면 그 장소에 서 있던 죽지 않은 캐릭터만 옮긴다.
         *     쓰러진 캐릭터도 옮겨진다(끌려간다). 두 장소가 맵의 장소인지는 게시할 때 본다. 길로 이어져 있지 않아도 된다.
         */
        "MoveEffect-Input": {
            /** From Place */
            from_place?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move";
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
        };
        /**
         * MoveEffect
         * @description 사건의 효과 하나: 캐릭터들을 맵의 한 장소(to_place)로 옮긴다(#367).
         *
         *     from_place 가 없으면 죽지 않은 캐릭터 모두를, 있으면 그 장소에 서 있던 죽지 않은 캐릭터만 옮긴다.
         *     쓰러진 캐릭터도 옮겨진다(끌려간다). 두 장소가 맵의 장소인지는 게시할 때 본다. 길로 이어져 있지 않아도 된다.
         */
        "MoveEffect-Output": {
            /** From Place */
            from_place?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move";
            /** To Place */
            to_place: string | null;
        };
        /**
         * MoveNpcEffect
         * @description 사건의 효과 하나: 인물(NPC) 하나(npc)를 맵의 한 장소(to_place)로 옮긴다(#282).
         *
         *     인물은 붙인 로어북의 인물 항목이다. 자리를 적지 않은 인물이면 그 뒤로 자리가 있는 인물이 된다.
         *     쓰러진 인물도 옮겨진다. 죽은 인물은 그 자리에 남는다. 길로 이어져 있지 않아도 된다.
         *     인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "MoveNpcEffect-Input": {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move_npc";
            /**
             * Npc
             * Format: uuid
             */
            npc: string;
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
        };
        /**
         * MoveNpcEffect
         * @description 사건의 효과 하나: 인물(NPC) 하나(npc)를 맵의 한 장소(to_place)로 옮긴다(#282).
         *
         *     인물은 붙인 로어북의 인물 항목이다. 자리를 적지 않은 인물이면 그 뒤로 자리가 있는 인물이 된다.
         *     쓰러진 인물도 옮겨진다. 죽은 인물은 그 자리에 남는다. 길로 이어져 있지 않아도 된다.
         *     인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "MoveNpcEffect-Output": {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "move_npc";
            /** Npc */
            npc: string;
            /** To Place */
            to_place: string;
        };
        /**
         * MoveOut
         * @description 한 칸 간 결과. 엔진이 정했다(app/rounds/map_actions.py). 넘기 판정(#281)이 있는 길이 아니면 판정이 없다.
         */
        MoveOut: {
            aid?: components["schemas"]["AidOut"] | null;
            carry?: components["schemas"]["CarryOut"] | null;
            /** Character Name */
            character_name: string;
            cross?: components["schemas"]["CrossOut"] | null;
            effect?: components["schemas"]["EffectOut"] | null;
            from: components["schemas"]["PlaceRefOut"] | null;
            /** Moved */
            moved: boolean;
            /** Reason */
            reason: string | null;
            to: components["schemas"]["PlaceRefOut"];
            /**
             * Traps
             * @default []
             */
            traps: components["schemas"]["TrapSprungOut"][];
            /** Travel Minutes */
            travel_minutes?: number | null;
            /**
             * Unbarred
             * @default false
             */
            unbarred: boolean;
            /**
             * Unlocked
             * @default false
             */
            unlocked: boolean;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * MoveOutcome
         * @description 가는 행동의 결과.
         */
        MoveOutcome: {
            move: components["schemas"]["MoveOut"];
        };
        /**
         * NameAction
         * @description 지목하는 행동. 인물의 진짜 이름을 짚는다.
         *
         *     npc 를 적으면 "이번 장면의 이 인물의 이름은 이것이다"다. 비우면 "이런 이름의 인물이 있다"다.
         *     장면에 없는 인물도 이름으로 짚을 수 있다. 맞으면 그 인물이 진짜 이름으로 불리기 시작한다.
         */
        NameAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "name";
            /** Name */
            name: string;
            /** Npc */
            npc?: string | null;
        };
        /**
         * NamingOut
         * @description 지목의 결과. 엔진이 정한 것이다(app/rounds/naming.py). 주사위를 굴리지 않았다.
         */
        NamingOut: {
            /** Correct */
            correct: boolean;
            /** Entry Id */
            entry_id: string | null;
            /** Guess */
            guess: string;
            /** Label */
            label: string | null;
            /** Name */
            name: string | null;
            /** Newly */
            newly: boolean;
        };
        /**
         * NamingOutcome
         * @description 지목하는 행동의 결과. 판정의 결과(CheckOutcome)와 달리 굴림이 없다.
         */
        NamingOutcome: {
            naming: components["schemas"]["NamingOut"];
        };
        /**
         * NarrationGuide
         * @description 서술 지침(#616). 이 규칙으로 하는 판을 어떤 분위기로, 판정 결과를 어떻게 그리는가, 무엇을 하지 않는가.
         *
         *     엔진은 보지 않는다. 서술자의 시스템 지시에 들어갈 뿐이다(app/rounds/prompt.py).
         *     판정을 바꾸지 못한다. 성공과 실패는 엔진이 이미 정했고, 지침은 그것을 그리는 법만 말한다.
         *     결과 단계마다 지침은 하나다. 적지 않은 단계는 공통의 지시대로 그린다.
         */
        NarrationGuide: {
            /** Avoid */
            avoid: string[];
            /** Outcomes */
            outcomes: components["schemas"]["OutcomeGuide"][];
            /** Tone */
            tone: string;
        };
        /**
         * NarrationModelOut
         * @description 고를 수 있는 서술 모델 하나와 1인 1라운드의 값.
         *
         *     credits 는 결제 서버가 정한 값(글자, "120")이다. 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
         *     tier 가 premium 이면 골드(유료 크레딧)로만 낸다. grade 는 화면의 묶음(basic, standard, premium)이다.
         */
        NarrationModelOut: {
            /** Credits */
            credits: string | null;
            /** Display Name */
            display_name: string;
            grade: components["schemas"]["Grade"];
            next: components["schemas"]["NextPriceOut"] | null;
            /** Options */
            options: components["schemas"]["StepPriceOut"][];
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
         * NarrationModelUpdate
         * @description 서술 모델과 단계를 바꿀 때 받는 값. 모델을 빼먹으면 거부한다. 비울 수 없다(서버의 기본 모델로 돌아가지 않는다).
         *
         *     단계(#387)는 모델과 함께 한 가격표를 고르는 것이다. 적지 않으면 0, 0(i0.o0)이다. 그 모델이 그 단계를 팔아야 한다.
         */
        NarrationModelUpdate: {
            /**
             * Input Step
             * @default 0
             */
            input_step: number;
            /** Narration Model */
            narration_model: string;
            /**
             * Output Step
             * @default 0
             */
            output_step: number;
        };
        /**
         * NarrationModelsOut
         * @description 고를 수 있는 서술 모델들. free 는 결제 서버 없이 도는 서버라 값이 없다는 뜻이다.
         */
        NarrationModelsOut: {
            /** Free */
            free: boolean;
            /** Models */
            models: components["schemas"]["NarrationModelOut"][];
        };
        /**
         * NarrationStyle
         * @description GM 의 서술 문체. 시나리오의 제작자가 하나를 추천하고, 테이블의 방장이 고를 수 있다.
         *
         *     값마다 서술자에게 주는 지시가 다르다(app/rounds/prompt.py). 화면에 보이는 이름은 화면이 정한다.
         *     값의 이름은 독자가 아니라 쓰는 기법을 가리킨다.
         * @enum {string}
         */
        NarrationStyle: "none" | "classic" | "web_novel" | "hardboiled" | "emotional" | "action" | "dopamine" | "literary";
        /**
         * NarrationStyleUpdate
         * @description 서술 문체를 바꿀 때 받는 값. null 을 보내면 판의 추천 문체로 돌린다. 칸을 빼먹으면 거부한다.
         */
        NarrationStyleUpdate: {
            narration_style: components["schemas"]["NarrationStyle"] | null;
        };
        /**
         * NaturalArmor
         * @description 몬스터의 한 부위의 타고난 방어(#276). 칸(slot)은 룰북의 장비의 칸이다. 룰북에 있는지는 게시할 때 본다.
         */
        NaturalArmor: {
            /** Defense */
            defense: number;
            /** Slot */
            slot: string;
        };
        /**
         * NaturalArmorSnapshot
         * @description 몬스터의 한 부위의 타고난 방어(#276). 칸은 판 안의 규칙의 장비의 칸이다.
         */
        NaturalArmorSnapshot: {
            /** Defense */
            defense: number;
            /** Slot */
            slot: string;
        };
        /**
         * NaturalRecovery
         * @description 저절로 회복하기. 게임 안의 시계가 every_minutes 분의 눈금을 하나 지날 때마다 heal 등급만큼 회복한다.
         *
         *     눈금은 1일째 0시부터 센다. 한 장면에 지난 눈금의 수만큼 굴린다. 짧은 라운드가 이어져도 눈금을 지나면 회복한다.
         */
        NaturalRecovery: {
            /** Every Minutes */
            every_minutes: number;
            /** Heal */
            heal: string;
        };
        /**
         * Nature
         * @description 성질 하나(#799, #886). 독, 기절, 화염 같은 것이다. 룰북이 정한다. 개수도 이름도 제작자의 것이다.
         *
         *     부상(injuries[].natures)이 성질을 가지고, 몬스터는 성질에 면역이다(타입마다의 monster_immunities, 시트의 immune).
         *     category 는 묶음의 이름(원소, 상태이상, 몸)이다. 화면에서 묶어 보여 주고 서술에 준다. 엔진은 보지 않는다.
         */
        Nature: {
            /** Category */
            category?: string | null;
            /** Key */
            key: string;
            /** Name */
            name: string;
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
         * NpcAttitude
         * @description NPC 가 일행을 대하는 태도(#474). 판의 인물(npc_sheets)에 처음 태도를 적고, 테이블에서 엔진이 바꾼다.
         *
         *     정확해야 하는 값이라 서술(AI)에 맡기지 않는다. 서술에는 사실로 준다. 방장도 바꾸지 못한다.
         * @enum {string}
         */
        NpcAttitude: "friendly" | "neutral" | "wary" | "hostile";
        /**
         * NpcCaught
         * @description NPC 에게서 훔치다 들켰을 때 그 NPC 가 어떻게 나오는가(#457). 판의 인물(npc_sheets)마다 작성자가 정한다.
         *
         *     들키면 늘 적대가 된다. hostile 은 적대만, fight 는 적대하고 싸움이 붙는다(싸운 것으로 친다).
         *     누가 어떻게 나올지는 엔진이 시트를 보고 정한다. 서술(AI)이 정하지 않는다.
         * @enum {string}
         */
        NpcCaught: "hostile" | "fight";
        /**
         * NpcEffectOut
         * @description 판정의 결과로 NPC 의 상태가 바뀐 것. 엔진이 정한 것이다.
         *
         *     HP 의 숫자(바뀌기 전과 뒤, 최대)는 싣지 않는다. GM 만 안다. 주사위의 눈과 양, 바뀐 생사는 보인다.
         */
        NpcEffectOut: {
            /** Amount */
            amount: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            injury_roll?: components["schemas"]["InjuryRollOut"] | null;
            kind: components["schemas"]["ChangeKind"];
            /** Lethal */
            lethal: boolean;
            /** Magnitude */
            magnitude: string;
            /** Name */
            name: string;
            nature?: components["schemas"]["DamageNatureOut"] | null;
            /** Rolls */
            rolls: number[];
            status: components["schemas"]["NpcStatus"];
        };
        /**
         * NpcPlace
         * @description 인물의 자리 하나(#282). 붙인 로어북의 인물 항목 하나(entry_id)가 처음에 맵의 장소 하나(place_id)에 있다.
         *
         *     자리가 있는 인물은 캐릭터가 그 장소에 서 있을 때 장면에 나오고, 같은 장소에서만 겨눈다. 서술이 불러내지 못한다.
         *     NPC 시트가 없는 인물도 자리를 적을 수 있다. 인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "NpcPlace-Input": {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * NpcPlace
         * @description 인물의 자리 하나(#282). 붙인 로어북의 인물 항목 하나(entry_id)가 처음에 맵의 장소 하나(place_id)에 있다.
         *
         *     자리가 있는 인물은 캐릭터가 그 장소에 서 있을 때 장면에 나오고, 같은 장소에서만 겨눈다. 서술이 불러내지 못한다.
         *     NPC 시트가 없는 인물도 자리를 적을 수 있다. 인물이 인물 항목인지, 장소가 맵의 장소인지는 게시할 때 본다.
         */
        "NpcPlace-Output": {
            /** Entry Id */
            entry_id: string;
            /** Place Id */
            place_id: string;
        };
        /**
         * NpcPlaceSnapshot
         * @description 인물의 자리 하나(#282). 판 안의 인물 항목 하나(entry_id)가 처음에 판 안의 장소 항목 하나(place_id)에 있다.
         */
        NpcPlaceSnapshot: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * NpcSheet
         * @description NPC 시트 하나. 붙인 로어북의 인물 항목 하나(entry_id)에 숫자와 처음 태도와 지닌 물건을 준다.
         *
         *     attitude 는 일행을 처음 어떻게 대하는가다(우호, 중립(기본), 적대). 테이블에서는 엔진이 바꾼다(#474).
         *     지닌 물건(장비와 소지품)과 둔한지는 몬스터 시트와 같은 모양이다(#457). 숨긴 소지품은 없다. 몬스터처럼 보인다.
         *     on_caught 는 훔치다 들켰을 때다. 늘 적대가 되고, fight 면 싸움도 붙는다(기본 hostile, 적대만).
         *     attacks 는 공격들이다. 몬스터 시트와 같은 모양이다(#487). 싸움이 붙은 적대 인물이 라운드의 차례에 쓴다(#487 2/2).
         *     merchant 는 상인인지다(#278). 상인은 소지품(inventory) 중 값이 있는 물건을 팔고, 값이 있는 물건을 사 준다.
         *     소지품의 개수가 곧 재고다. 장비는 팔지 않는다.
         *
         *     프리젠과 달리 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 이 칸을 만들지 않으면 된다(기본 NPC 시트를 쓴다).
         *     가리키는 항목이 붙인 로어북에 있는지, 인물인지, 시트가 규칙에 맞는지는 게시할 때 본다.
         *     로어북도 룰북도 나중에 바꿀 수 있어서 지금 정할 수 없다.
         */
        "NpcSheet-Input": {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["MonsterAttack-Input"][];
            /** @default neutral */
            attitude: components["schemas"]["NpcAttitude"];
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItem-Input"][];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItem-Input"][];
            /**
             * Merchant
             * @default false
             */
            merchant: boolean;
            /** Nature */
            nature?: string | null;
            /** @default hostile */
            on_caught: components["schemas"]["NpcCaught"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
        };
        /**
         * NpcSheet
         * @description NPC 시트 하나. 붙인 로어북의 인물 항목 하나(entry_id)에 숫자와 처음 태도와 지닌 물건을 준다.
         *
         *     attitude 는 일행을 처음 어떻게 대하는가다(우호, 중립(기본), 적대). 테이블에서는 엔진이 바꾼다(#474).
         *     지닌 물건(장비와 소지품)과 둔한지는 몬스터 시트와 같은 모양이다(#457). 숨긴 소지품은 없다. 몬스터처럼 보인다.
         *     on_caught 는 훔치다 들켰을 때다. 늘 적대가 되고, fight 면 싸움도 붙는다(기본 hostile, 적대만).
         *     attacks 는 공격들이다. 몬스터 시트와 같은 모양이다(#487). 싸움이 붙은 적대 인물이 라운드의 차례에 쓴다(#487 2/2).
         *     merchant 는 상인인지다(#278). 상인은 소지품(inventory) 중 값이 있는 물건을 팔고, 값이 있는 물건을 사 준다.
         *     소지품의 개수가 곧 재고다. 장비는 팔지 않는다.
         *
         *     프리젠과 달리 시트를 비워 둘 수 없다. 숫자를 줄 생각이 없으면 이 칸을 만들지 않으면 된다(기본 NPC 시트를 쓴다).
         *     가리키는 항목이 붙인 로어북에 있는지, 인물인지, 시트가 규칙에 맞는지는 게시할 때 본다.
         *     로어북도 룰북도 나중에 바꿀 수 있어서 지금 정할 수 없다.
         */
        "NpcSheet-Output": {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["MonsterAttack-Output"][];
            /** @default neutral */
            attitude: components["schemas"]["NpcAttitude"];
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /** Entry Id */
            entry_id: string;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItem-Output"][];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItem-Output"][];
            /**
             * Merchant
             * @default false
             */
            merchant: boolean;
            /** Nature */
            nature?: string | null;
            /** @default hostile */
            on_caught: components["schemas"]["NpcCaught"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
        };
        /**
         * NpcSheetSnapshot
         * @description NPC 시트 하나. 판 안의 로어북 인물 항목 하나(entry_id)의 숫자와 처음 태도와 지닌 물건이다.
         */
        NpcSheetSnapshot: {
            /**
             * Attacks
             * @default []
             */
            attacks: components["schemas"]["AttackSnapshot"][];
            /** @default neutral */
            attitude: components["schemas"]["NpcAttitude"];
            /**
             * Dull
             * @default false
             */
            dull: boolean;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Equipment
             * @default []
             */
            equipment: components["schemas"]["CarriedItemSnapshot"][];
            /**
             * Inventory
             * @default []
             */
            inventory: components["schemas"]["CarriedItemSnapshot"][];
            /**
             * Merchant
             * @default false
             */
            merchant: boolean;
            /** Nature */
            nature?: string | null;
            /** @default hostile */
            on_caught: components["schemas"]["NpcCaught"];
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            sheet: components["schemas"]["Sheet"];
        };
        /**
         * NpcStatus
         * @description NPC 의 생사. HP 와 따로 적는다. HP 가 0 인 NPC 는 쓰러졌거나 죽었는데, HP 만으로는 둘을 가를 수 없다.
         *
         *     쓰러진 NPC 는 혼자서 깨어나지 못한다(의식이 없다). 죽음의 굴림은 없다. 회복을 받으면 일어난다.
         *     죽은 NPC 는 되돌리지 못한다.
         * @enum {string}
         */
        NpcStatus: "alive" | "downed" | "dead";
        /**
         * OperatorMember
         * @description 테이블에 앉은 사람 한 명.
         */
        OperatorMember: {
            /**
             * Joined At
             * Format: date-time
             */
            joined_at: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * OperatorTable
         * @description 운영자가 보는 테이블. 앉은 사람이 보는 것과 달리 굳힌 판의 내용(content)을 통째로 싣는다.
         *
         *     content 에는 룰북의 진행 지침, 세계관의 GM 전용 설정, 로어북, GM 메모처럼 AI 에 들어가는 글이 모두 있다.
         */
        OperatorTable: {
            /** Content */
            content: {
                [key: string]: unknown;
            };
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Ended At */
            ended_at: string | null;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Members */
            members: components["schemas"]["OperatorMember"][];
            /** Rating */
            rating: string;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * OperatorWhisperPage
         * @description 테이블의 귓속말 전부의 한 쪽. 쪽지함이 아니라 테이블 전체라 total 로 넘긴다.
         */
        OperatorWhisperPage: {
            /** Items */
            items: components["schemas"]["WhisperOut"][];
            /** Total */
            total: number;
        };
        /**
         * Outcome
         * @description 판정 결과의 단계. 엔진의 판정(app/engine/check.py)이 내는 것이다.
         *
         *     지금의 판정은 성공과 실패 둘이다. 부분 성공 같은 단계는 엔진이 그 단계를 정하게 될 때 더한다.
         * @enum {string}
         */
        Outcome: "success" | "failure";
        /**
         * OutcomeGuide
         * @description 판정 결과 한 단계를 어떻게 그리는가. 예: 실패하면 상황이 나빠지는 것을 감각으로 보여 준다.
         */
        OutcomeGuide: {
            /** Guide */
            guide: string;
            outcome: components["schemas"]["Outcome"];
        };
        /**
         * PastTableOut
         * @description 내가 떠난 테이블 하나(#428). 떠난 때까지의 기록을 읽는 길(GET /tables/past/{table_id}/events)로 간다.
         *
         *     떠난 뒤의 일은 싣지 않는다. 테이블이 지금 어떤 상태인지, 누가 남았는지도 싣지 않는다.
         */
        PastTableOut: {
            /** Character Name */
            character_name: string | null;
            kind: components["schemas"]["DepartureKind"];
            /** Last Sequence */
            last_sequence: number;
            /**
             * Left At
             * Format: date-time
             */
            left_at: string;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /**
             * Table Id
             * Format: uuid
             */
            table_id: string;
            /** Title */
            title: string;
        };
        /**
         * PastTablePage
         * @description 내가 떠난 테이블 목록의 한 쪽. 최근에 떠난 것부터다.
         */
        PastTablePage: {
            /** Items */
            items: components["schemas"]["PastTableOut"][];
            /** Total */
            total: number;
        };
        /**
         * PatientOut
         * @description 치료받은 쪽. 캐릭터면 user_id 와 character_name, NPC 면 entry_id 와 장면의 호칭(name)이 채워진다.
         */
        PatientOut: {
            /** Character Name */
            character_name?: string | null;
            /** Entry Id */
            entry_id?: string | null;
            /** Name */
            name?: string | null;
            /** User Id */
            user_id?: string | null;
        };
        /**
         * PayAction
         * @description 가진 돈 amount 를 앉은 다른 사람(target)에게 건네는 행동(app/rounds/trades.py, #278). 판정이 없다.
         */
        PayAction: {
            /** Amount */
            amount: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "pay";
            /**
             * Target
             * Format: uuid
             */
            target: string;
        };
        /**
         * PayOut
         * @description 돈을 건넨 결과(#278). 엔진이 정했다(app/rounds/trades.py). 판정이 없다.
         *
         *     paid 가 거짓이면 reason 이 있다: not_enough_money, target_gone(받을 사람이 떠났거나 죽었다),
         *     too_much_money(받을 사람이 더 가질 수 없었다).
         *     remaining 은 건넨 뒤에 가진 돈, target_total 은 받은 사람이 가진 돈이다. 받을 사람이 떠났으면 None 이다.
         */
        PayOut: {
            /** Amount */
            amount: number;
            /** Character Name */
            character_name: string;
            /** Paid */
            paid: boolean;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            target: components["schemas"]["ItemPersonOut"];
            /** Target Total */
            target_total: number | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * PayOutcome
         * @description 돈을 건네는 행동의 결과.
         */
        PayOutcome: {
            pay: components["schemas"]["PayOut"];
        };
        /**
         * PersonOut
         * @description 이번 장면의 인물 하나. 행동으로 겨눌 수 있는 NPC 다(죽은 인물은 겨누지 못한다).
         *
         *     자리가 있는 인물(place_id)은 같은 장소에 선 캐릭터만 겨눈다(#282). 자리가 없는 인물은 누구나 겨눈다.
         */
        PersonOut: {
            attitude: components["schemas"]["NpcAttitude"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Injuries */
            injuries: string[];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["CarriedOut"][];
            /**
             * Merchant
             * @default false
             */
            merchant: boolean;
            /** Name */
            name: string;
            /** Named */
            named: boolean;
            /** Place Id */
            place_id?: string | null;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceOut"][];
            status: components["schemas"]["NpcStatus"];
        };
        /**
         * PersonaOut
         * @description 보관한 캐릭터 하나. 주인에게만 보인다.
         */
        PersonaOut: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            } | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Rulebook Title */
            rulebook_title: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * PersonaPage
         * @description 보관함 목록의 한 쪽.
         */
        PersonaPage: {
            /** Items */
            items: components["schemas"]["PersonaOut"][];
            /** Total */
            total: number;
        };
        /**
         * PersonaWrite
         * @description 보관함에 캐릭터를 만들거나 고칠 때 받는 값. 고칠 때는 보낸 것으로 통째로 바꾼다.
         *
         *     능력치는 비워도 된다. 글만 보관한 캐릭터는 테이블에서 숫자를 정한다.
         *     룰북의 제목은 받지 않는다. 테이블에서 저장할 때 서버가 적는다.
         */
        PersonaWrite: {
            /** Abilities */
            abilities?: {
                [key: string]: number;
            } | null;
            /**
             * Description
             * @default
             */
            description: string;
            /** Name */
            name: string;
        };
        /**
         * PickAction
         * @description 지금 서 있는 장소에 닿은 길의 잠긴 자물쇠를 따는 행동(#281). 판에 적힌 따는 판정(능력, 난이도)으로 굴린다.
         *
         *     판이 도구를 요구하면 따기를 거드는 물건(item)을 붙여야 딴다(#802). 성공하면 자물쇠가 열린다. 지나가지는 않는다.
         */
        PickAction: {
            /** Item */
            item?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "pick";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * PickCheck
         * @description 자물쇠를 따는 판정(#281). 행동 '따기'가 이 능력과 난이도로 굴린다. 성공하면 자물쇠가 열린다.
         *
         *     needs_tool 이면 도구가 있어야 딴다(#802). 도구는 그 행동을 거드는 물건(아이템 규칙의 aids)이면 어느 것이든 된다.
         *     플레이어가 행동에 붙인다. 보정과 없어지는 방식은 물건이 정한다.
         *     예전의 특정 도구(tool)는 이것과 그 물건의 거들기가 됐다.
         *     능력치와 난이도가 룰북에 있는지는 게시할 때 본다.
         */
        PickCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Needs Tool
             * @default false
             */
            needs_tool: boolean;
        };
        /**
         * PickSnapshot
         * @description 자물쇠를 따는 판정(#281). 능력치, 난이도의 이름과 도구가 있어야 하는가(#802).
         *
         *     도구는 그 행동을 거드는 물건이면 어느 것이든 된다. 형식 64 보다 옛 판의 특정 도구는 이것과 그 물건의 거들기가 된다.
         */
        PickSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Needs Tool
             * @default false
             */
            needs_tool: boolean;
        };
        /**
         * PierceOut
         * @description 관통 굴림(#276). 눈 + 관통력(ap)이 target(그 부위의 방어 + 룰북의 기준값) 이상이면 관통이다.
         */
        PierceOut: {
            /** Ap */
            ap: number;
            /** Pierced */
            pierced: boolean;
            /** Roll */
            roll: number;
            /** Target */
            target: number;
        };
        /**
         * PlaceItem
         * @description 장소에 놓인 물건 한 줄. 맵의 장소 하나(place_id)에 물건 하나(entry_id)가 count 개 있다(#279).
         *
         *     visibility 는 플레이어가 언제 아는가다(기본은 보임, PlaceItemVisibility). 보이는 물건은 줍기(take)로 가져간다.
         *     숨긴 물건에는 찾는 판정(find)이 있어야 하고, 보이는 물건에는 없다. 숨긴 길과 같다.
         *     장소가 맵의 장소인지, 물건이 붙인 로어북의 물건 항목인지, 판정이 룰북의 규칙에 있는지는 게시할 때 본다.
         */
        "PlaceItem-Input": {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            find?: components["schemas"]["FindCheck"] | null;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
            /** @default open */
            visibility: components["schemas"]["PlaceItemVisibility"];
        };
        /**
         * PlaceItem
         * @description 장소에 놓인 물건 한 줄. 맵의 장소 하나(place_id)에 물건 하나(entry_id)가 count 개 있다(#279).
         *
         *     visibility 는 플레이어가 언제 아는가다(기본은 보임, PlaceItemVisibility). 보이는 물건은 줍기(take)로 가져간다.
         *     숨긴 물건에는 찾는 판정(find)이 있어야 하고, 보이는 물건에는 없다. 숨긴 길과 같다.
         *     장소가 맵의 장소인지, 물건이 붙인 로어북의 물건 항목인지, 판정이 룰북의 규칙에 있는지는 게시할 때 본다.
         */
        "PlaceItem-Output": {
            /**
             * Count
             * @default 1
             */
            count: number;
            /** Entry Id */
            entry_id: string;
            find?: components["schemas"]["FindCheck"] | null;
            /** Place Id */
            place_id: string;
            /** @default open */
            visibility: components["schemas"]["PlaceItemVisibility"];
        };
        /**
         * PlaceItemOut
         * @description 장소에 보이게 놓인 물건 한 가지. 같은 물건은 합친 개수다. 이름은 판의 로어북 물건 항목의 이름이다.
         */
        PlaceItemOut: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
        };
        /**
         * PlaceItemSnapshot
         * @description 장소에 놓인 물건 한 줄. 판 안의 장소 항목 하나(place_id)에 판 안의 물건 항목 하나(entry_id)가 count 개 있다.
         *
         *     숨긴 물건(hidden)은 찾는 판정(find)으로 드러난다. 판의 줄 순서가 테이블의 남은 개수(table_place_items)의 번호다.
         */
        PlaceItemSnapshot: {
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            find?: components["schemas"]["FindSnapshot"] | null;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
            /** @default open */
            visibility: components["schemas"]["PlaceItemVisibility"];
        };
        /**
         * PlaceItemVisibility
         * @description 장소에 놓인 물건을 플레이어가 언제 아는가. 제작자가 줄마다 정한다.
         *
         *     숨긴 물건은 숨긴 길과 같다. 방장도 모른다. 시나리오를 만든 사람과 AI GM 만 안다.
         * @enum {string}
         */
        PlaceItemVisibility: "open" | "hidden";
        /**
         * PlaceOut
         * @description 아는 장소 하나. 이름은 판의 로어북 장소 항목의 이름이다.
         *
         *     장소의 글은 싣지 않는다. 로어북은 AI 가 읽는 설정이다.
         *     items 는 그곳에 보이게 놓인 물건들이다. 누군가 서 본 장소만 싣는다. 숨긴 물건은 싣지 않는다
         *     (app/tables/place_items.py). 캐릭터가 내려놓은 것(put_down)도 여기 보인다. 줍기(take)로 가져간다.
         *     cover 는 그 장소의 숨을 곳이 얼마나 좋은지다(#276). 세이브 방식의 판에서 엄폐하면 이 값으로 커버 세이브를 받는다.
         *     커버가 없는 곳이면 0 이다. traps 는 찾아낸 덫들이다(#806 ①-b).
         */
        PlaceOut: {
            /**
             * Cover
             * @default 0
             */
            cover: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["PlaceItemOut"][];
            /** Name */
            name: string;
            /**
             * Traps
             * @default []
             */
            traps: components["schemas"]["KnownTrapOut"][];
        };
        /**
         * PlaceRefOut
         * @description 맵의 장소 하나. 판의 로어북 장소 항목과 그 이름이다. 아는 장소만 실린다.
         */
        PlaceRefOut: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
        };
        /**
         * PlacedTrap
         * @description 미리 놓인 덫 하나(#806 ②). 그 장소(place_id)에 덫 물건(entry_id) 하나가 놓여 있다.
         *
         *     물건은 아이템 규칙에 덫(trap)을 적은 물건이어야 하고, 장소는 맵의 장소여야 한다(게시할 때 본다).
         *     known 이면 처음부터 테이블이 아는 덫이다(경고 표지가 붙은 함정). 캐릭터가 밟지 않고, 해제할 수 있다.
         *     아니면(기본) 숨긴 덫이다. 찾기 행동으로 찾는다. 한 장소에 여럿을 놓을 수 있다.
         */
        "PlacedTrap-Input": {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Known
             * @default false
             */
            known: boolean;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * PlacedTrap
         * @description 미리 놓인 덫 하나(#806 ②). 그 장소(place_id)에 덫 물건(entry_id) 하나가 놓여 있다.
         *
         *     물건은 아이템 규칙에 덫(trap)을 적은 물건이어야 하고, 장소는 맵의 장소여야 한다(게시할 때 본다).
         *     known 이면 처음부터 테이블이 아는 덫이다(경고 표지가 붙은 함정). 캐릭터가 밟지 않고, 해제할 수 있다.
         *     아니면(기본) 숨긴 덫이다. 찾기 행동으로 찾는다. 한 장소에 여럿을 놓을 수 있다.
         */
        "PlacedTrap-Output": {
            /** Entry Id */
            entry_id: string;
            /**
             * Known
             * @default false
             */
            known: boolean;
            /** Place Id */
            place_id: string;
        };
        /**
         * PlacedTrapSnapshot
         * @description 미리 놓인 덫 하나(#806 ②). 판 안의 장소 항목(place_id)에 덫 물건(entry_id, 아이템 규칙에 trap 이 있다)이 놓였다.
         *     known 이면 처음부터 테이블이 안다.
         */
        PlacedTrapSnapshot: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Known
             * @default false
             */
            known: boolean;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
        };
        /**
         * PlayerMadeHp
         * @description 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 기준값과 상한을 함께 보낸다.
         *
         *     최대 HP = 기준값 + 능력치의 보정. 상한을 넘지 않는다. 어느 능력치의 보정인지는 룰북의 규칙이 정한다.
         *     상한을 기준값과 같게 두면 보정은 깎기만 한다.
         */
        PlayerMadeHp: {
            /** Base */
            base: number;
            /** Cap */
            cap: number;
        };
        /**
         * PlayerMadeHpSnapshot
         * @description 플레이어가 능력치를 정한 캐릭터의 최대 HP 를 구하는 값. 기준값과 상한이다.
         */
        PlayerMadeHpSnapshot: {
            /** Base */
            base: number;
            /** Cap */
            cap: number;
        };
        /**
         * PlayersSnapshot
         * @description 추천 인원.
         */
        PlayersSnapshot: {
            /** Max */
            max: number;
            /** Min */
            min: number;
        };
        /**
         * PointBuy
         * @description 점수제. 정해진 총점 안에서 능력치의 점수를 사는 방식이다.
         *
         *     고를 수 있는 점수는 값표에 있는 것뿐이다. 값표에 없는 점수는 살 수 없다.
         *     높은 점수일수록 비싸게 매길 수 있다. 값이 점수에 비례하지 않아도 된다.
         */
        PointBuy: {
            /** Budget */
            budget: number;
            /** Costs */
            costs: components["schemas"]["PointCost"][];
        };
        /**
         * PointCost
         * @description 점수제의 값표 한 줄. 이 점수를 고르는 데 드는 값이다. 예: 점수 14 는 7.
         */
        PointCost: {
            /** Cost */
            cost: number;
            /** Score */
            score: number;
        };
        /**
         * Pregen
         * @description 프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다.
         *
         *     이름과 설명은 플레이어가 만드는 캐릭터와 칸이 같다. 그래서 골라서 그대로 자기 캐릭터로 가져갈 수 있다.
         *     시트는 그 캐릭터의 숫자다. 초안일 때는 비워 둘 수 있다. 게시할 때 있는지, 룰북의 규칙에 맞는지 검사한다.
         *     여기서는 시트의 모양만 본다. 룰북은 나중에 붙이거나 바꿀 수 있어서, 규칙에 맞는지는 지금 정할 수 없다.
         */
        "Pregen-Input": {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemStack-Input"][];
            /**
             * Money
             * @default 0
             */
            money: number;
            /** Name */
            name: string;
            sheet?: components["schemas"]["CharacterSheet"] | null;
        };
        /**
         * Pregen
         * @description 프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다.
         *
         *     이름과 설명은 플레이어가 만드는 캐릭터와 칸이 같다. 그래서 골라서 그대로 자기 캐릭터로 가져갈 수 있다.
         *     시트는 그 캐릭터의 숫자다. 초안일 때는 비워 둘 수 있다. 게시할 때 있는지, 룰북의 규칙에 맞는지 검사한다.
         *     여기서는 시트의 모양만 본다. 룰북은 나중에 붙이거나 바꿀 수 있어서, 규칙에 맞는지는 지금 정할 수 없다.
         */
        "Pregen-Output": {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemStack-Output"][];
            /**
             * Money
             * @default 0
             */
            money: number;
            /** Name */
            name: string;
            sheet?: components["schemas"]["CharacterSheet"] | null;
        };
        /**
         * PregenChoice
         * @description 고를 수 있는 프리젠 하나. 누가 이미 가져갔는지 함께 알려 준다.
         */
        PregenChoice: {
            /** Dead */
            dead: boolean;
            /** Description */
            description: string;
            /** Name */
            name: string;
            sheet: components["schemas"]["CharacterSheet"];
            /** Taken By */
            taken_by: string | null;
        };
        /**
         * PregenSnapshot
         * @description 프리젠 하나. 제작자가 미리 만들어 둔 캐릭터다. 판 안의 프리젠은 모두 시트가 있다.
         *
         *     items 와 money 는 이 프리젠을 고른 사람이 시작할 때 더 받는 소지품과 돈이다.
         */
        PregenSnapshot: {
            /** Description */
            description: string;
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemStackSnapshot"][];
            /**
             * Money
             * @default 0
             */
            money: number;
            /** Name */
            name: string;
            sheet: components["schemas"]["CharacterSheet"];
        };
        /**
         * PublicListing
         * @description 다른 사용자가 공개된 시나리오를 볼 때의 값. 목록과 상세가 같은 모양이다.
         *
         *     여기 적힌 칸만 나간다. 초안의 내용, 판의 굳힌 내용, 공개하지 않은 판의 정보는 나가지 않는다.
         */
        PublicListing: {
            /**
             * Creator Id
             * Format: uuid
             */
            creator_id: string;
            /** Description */
            description: string;
            genre: components["schemas"]["Genre"];
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            rating: components["schemas"]["Rating"];
            recommended_players: components["schemas"]["RecommendedPlayers"];
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Tagline */
            tagline: string;
            /** Tags */
            tags: string[];
            /** Title */
            title: string;
            /** Version */
            version: number;
            /** Version Note */
            version_note: string;
        };
        /**
         * PublicListingDetail
         * @description 공개된 시나리오 하나를 볼 때의 값(#428). 목록의 칸에, 테이블을 만들기 전에 고를 것들이 더 있다.
         *
         *     테이블을 만들 때(POST /tables) 스타팅의 순번(opening_index), 캐릭터 방식(character_modes), 서술 모델을 고른다.
         *     남의 시나리오는 판을 읽을 수 없어서 고를 거리를 볼 길이 없었다. 공개 중인 판의 것이다.
         *     목록(PublicListingPage)에는 싣지 않는다. 스타팅은 다섯 개까지 하나에 2,000 자라 목록에 싣기에는 크다.
         *     GM 전용 글(진행 지침, GM 메모)과 판의 나머지(로어북, NPC, 몬스터, 퀘스트)는 싣지 않는다.
         */
        PublicListingDetail: {
            /** Abilities */
            abilities: components["schemas"]["Ability"][];
            /** Character Modes */
            character_modes: components["schemas"]["CharacterMode"][];
            /**
             * Creator Id
             * Format: uuid
             */
            creator_id: string;
            /** Description */
            description: string;
            genre: components["schemas"]["Genre"];
            /** Openings */
            openings: string[];
            /** Pregens */
            pregens: components["schemas"]["ListingPregen"][];
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            rating: components["schemas"]["Rating"];
            /** Recommended Narration Model */
            recommended_narration_model: string | null;
            recommended_players: components["schemas"]["RecommendedPlayers"];
            /** References Allowed */
            references_allowed: boolean;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Tagline */
            tagline: string;
            /** Tags */
            tags: string[];
            /** Title */
            title: string;
            /** Version */
            version: number;
            /** Version Note */
            version_note: string;
        };
        /**
         * PublicListingPage
         * @description 공개 목록의 한 쪽.
         */
        PublicListingPage: {
            /** Items */
            items: components["schemas"]["PublicListing"][];
            /** Total */
            total: number;
        };
        /**
         * PublicationUpdate
         * @description 공개할 판을 정할 때 받는 값. 판의 번호를 적는다.
         *
         *     비워서 보내면(null) 공개를 내린다.
         */
        PublicationUpdate: {
            /** Version */
            version: number | null;
        };
        /**
         * PublishCheck
         * @description 지금 게시하면 막히는 이유(#428). 게시하지 않고 미리 본다. 판을 만들지 않는다.
         *
         *     problems 는 게시가 409 로 돌려주는 것과 같은 이름들이다. 비어 있으면 지금 게시할 수 있다(ready).
         */
        PublishCheck: {
            /** Problems */
            problems: string[];
            /** Ready */
            ready: boolean;
        };
        /**
         * PublishingBanOut
         * @description 한 사람의 공개 금지.
         */
        PublishingBanOut: {
            /** Banned */
            banned: boolean;
            /**
             * Banned At
             * Format: date-time
             */
            banned_at: string;
            /** Banned By */
            banned_by: string | null;
            /** Lifted At */
            lifted_at: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * PutDownAction
         * @description 가진 물건(item) count 개를 지금 서 있는 장소에 내려놓는 행동(app/rounds/place_item_actions.py).
         *
         *     판정이 없다. 내려놓은 물건은 그 장소에 보이게 놓인 물건이 되어 누구나 줍기(take)로 가져간다.
         */
        PutDownAction: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "put_down";
        };
        /**
         * PutDownOut
         * @description 내려놓은 결과. 엔진이 정했다(app/rounds/place_item_actions.py). 판정이 없다.
         *
         *     put 이 참이면 그 장소에 보이게 놓였다. 차례가 왔을 때 그만큼 가지고 있지 않았으면 놓지 않았다(reason 이 not_held).
         */
        PutDownOut: {
            /** Character Name */
            character_name: string;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            place: components["schemas"]["PlaceRefOut"] | null;
            /** Put */
            put: boolean;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * PutDownOutcome
         * @description 내려놓는 행동의 결과.
         */
        PutDownOutcome: {
            put_down: components["schemas"]["PutDownOut"];
        };
        /**
         * QuestCondition
         * @description 퀘스트의 조건 하나. 종류(kind)마다 target 이 가리키는 것이 다르다(QuestConditionKind).
         *
         *     reach_place 는 장소 항목, defeat_monster 는 붙인 도감의 몬스터(시트를 적은 것),
         *     hold_item 과 lose_item 은 물건 항목,
         *     defeat_npc 와 npc_dead 는 인물 항목, quest_succeeded 와 quest_failed 는 다른 퀘스트(사건 항목)다.
         *     count 는 defeat_monster, hold_item, lose_item 만 쓴다. 나머지는 1 로 둔다.
         *     consume 은 hold_item 에만 쓴다. 참이면 이룰 때 그 물건을 count 개 일행의 소지품에서 가져간다(배달).
         *     일행이 고르게 나눠 낸다(app/rounds/quest_handover.py). 이루는 조건(conditions)에만 적는다.
         *     가리키는 것이 있는지, 맞는 종류인지, 이룰 수 있는지는 게시할 때 본다.
         */
        "QuestCondition-Input": {
            /**
             * Consume
             * @default false
             */
            consume: boolean;
            /**
             * Count
             * @default 1
             */
            count: number;
            kind: components["schemas"]["QuestConditionKind"];
            /**
             * Target
             * Format: uuid
             */
            target: string;
        };
        /**
         * QuestCondition
         * @description 퀘스트의 조건 하나. 종류(kind)마다 target 이 가리키는 것이 다르다(QuestConditionKind).
         *
         *     reach_place 는 장소 항목, defeat_monster 는 붙인 도감의 몬스터(시트를 적은 것),
         *     hold_item 과 lose_item 은 물건 항목,
         *     defeat_npc 와 npc_dead 는 인물 항목, quest_succeeded 와 quest_failed 는 다른 퀘스트(사건 항목)다.
         *     count 는 defeat_monster, hold_item, lose_item 만 쓴다. 나머지는 1 로 둔다.
         *     consume 은 hold_item 에만 쓴다. 참이면 이룰 때 그 물건을 count 개 일행의 소지품에서 가져간다(배달).
         *     일행이 고르게 나눠 낸다(app/rounds/quest_handover.py). 이루는 조건(conditions)에만 적는다.
         *     가리키는 것이 있는지, 맞는 종류인지, 이룰 수 있는지는 게시할 때 본다.
         */
        "QuestCondition-Output": {
            /**
             * Consume
             * @default false
             */
            consume: boolean;
            /**
             * Count
             * @default 1
             */
            count: number;
            kind: components["schemas"]["QuestConditionKind"];
            /** Target */
            target: string;
        };
        /**
         * QuestConditionKind
         * @description 퀘스트의 조건 하나가 무엇을 보는가. 엔진이 이미 아는 사실(상태)만 본다(app/rounds/quest_goals.py).
         *
         *     target 이 무엇을 가리키는지는 종류마다 다르다. 장소, 판의 몬스터, 물건, 인물, 다른 퀘스트(사건)다.
         *     다른 퀘스트를 보는 것(퀘스트 잇기)은 드러나는 조건(reveal)과 실패하는 조건(fail)에 쓴다.
         *     이루는 조건(conditions)에는 쓰지 않는다. 물건을 잃는 것(lose_item)은 실패하는 조건에만 쓴다(#367).
         * @enum {string}
         */
        QuestConditionKind: "reach_place" | "defeat_monster" | "hold_item" | "defeat_npc" | "npc_dead" | "lose_item" | "quest_succeeded" | "quest_failed";
        /**
         * QuestConditionSnapshot
         * @description 퀘스트의 조건 하나. target 은 종류마다 판 안의 장소 항목, 몬스터, 물건 항목, 인물 항목, 사건 항목(퀘스트)이다.
         *
         *     consume 은 물건 갖기(hold_item)를 이룰 때 그 물건을 가져가는지다(배달). 이루는 조건에만 있다.
         */
        QuestConditionSnapshot: {
            /**
             * Consume
             * @default false
             */
            consume: boolean;
            /**
             * Count
             * @default 1
             */
            count: number;
            kind: components["schemas"]["QuestConditionKind"];
            /**
             * Target
             * Format: uuid
             */
            target: string;
        };
        /**
         * QuestMatch
         * @description 퀘스트의 조건이 여럿일 때 언제 이룬 것인가.
         * @enum {string}
         */
        QuestMatch: "all" | "any";
        /**
         * QuestOut
         * @description 퀘스트 하나. 이름은 판의 로어북 사건 항목의 이름이다. 판의 순서로 싣는다.
         *
         *     사건의 글은 싣지 않는다. 로어북은 AI 가 읽는 설정이다. 숨긴(hidden) 것은 방장에게만 싣는다.
         */
        QuestOut: {
            due_at?: components["schemas"]["ClockTimeOut"] | null;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            status: components["schemas"]["QuestStatus"];
        };
        /**
         * QuestRule
         * @description 퀘스트 규칙 하나. 붙인 로어북의 사건 항목 하나(entry_id)가 퀘스트로서 어떤지 정한다.
         *
         *     start 는 테이블이 시작할 때의 상태다(숨김, 진행 중). reward 는 성공했을 때 받는 물건이다.
         *     reward_money 는 성공했을 때 받는 돈이다(#278). 살아 있는 캐릭터마다 이만큼 받는다. 0 이면 돈은 없다.
         *     time_limit_minutes 는 기한이다. 퀘스트가 드러난(진행 중이 된) 때부터 게임 안의 시간으로 센다.
         *     비우면 기한이 없다. 지나면 서버가 실패로 바꾼다(app/rounds/deadlines.py).
         *     conditions 는 이루는 조건이다. 라운드가 닫힐 때 엔진이 보고 채워졌으면 성공으로 바꾼다(app/rounds/quest_goals.py).
         *     match 는 조건이 여럿일 때 모두(all) 채워야 하는지, 하나라도(any) 채우면 되는지다.
         *     조건이 없으면 성공하지 않는다. 사람(방장, 장부 초안)은 퀘스트를 성공으로 바꾸지 못한다.
         *     reveal 은 숨긴 퀘스트가 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 엔진이 보고 드러낸다.
         *     숨긴 채로 시작하는 퀘스트에만 적는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)은 여기와 실패하는 조건에 쓴다.
         *     자기 자신을 보면 거부한다. 드러나는 조건이 없는 숨긴 퀘스트는 이루어야만 드러난다(드러내며 바로 성공).
         *     사람(방장, 장부 초안)은 퀘스트를 드러내지 못한다.
         *     fail 은 실패하는 조건, fail_match 는 그것을 맞추는 법이다(#367).
         *     진행 중인 퀘스트의 조건이 채워지면 엔진이 실패로 바꾼다.
         *     같은 라운드에 이루는 조건도 채워졌으면 성공이 먼저다. 물건을 잃는 것(lose_item)은 여기에만 쓴다.
         *     조건이 없으면 기한으로만 실패한다. 사람(방장)은 퀘스트를 실패로 바꾸지 못한다.
         *     규칙이 없는 사건 항목은 숨긴 채로 시작하고 보상과 기한과 조건이 없다.
         *     가리키는 사건과 보상의 물건이 붙인 로어북에 있는지는 게시할 때 본다.
         */
        "QuestRule-Input": {
            /**
             * Conditions
             * @default []
             */
            conditions: components["schemas"]["QuestCondition-Input"][];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Fail
             * @default []
             */
            fail: components["schemas"]["QuestCondition-Input"][];
            /** @default all */
            fail_match: components["schemas"]["QuestMatch"];
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /**
             * Reveal
             * @default []
             */
            reveal: components["schemas"]["QuestCondition-Input"][];
            /** @default all */
            reveal_match: components["schemas"]["QuestMatch"];
            /**
             * Reward
             * @default []
             */
            reward: components["schemas"]["ItemStack-Input"][];
            /**
             * Reward Money
             * @default 0
             */
            reward_money: number;
            /** @default hidden */
            start: components["schemas"]["QuestStart"];
            /** Time Limit Minutes */
            time_limit_minutes?: number | null;
        };
        /**
         * QuestRule
         * @description 퀘스트 규칙 하나. 붙인 로어북의 사건 항목 하나(entry_id)가 퀘스트로서 어떤지 정한다.
         *
         *     start 는 테이블이 시작할 때의 상태다(숨김, 진행 중). reward 는 성공했을 때 받는 물건이다.
         *     reward_money 는 성공했을 때 받는 돈이다(#278). 살아 있는 캐릭터마다 이만큼 받는다. 0 이면 돈은 없다.
         *     time_limit_minutes 는 기한이다. 퀘스트가 드러난(진행 중이 된) 때부터 게임 안의 시간으로 센다.
         *     비우면 기한이 없다. 지나면 서버가 실패로 바꾼다(app/rounds/deadlines.py).
         *     conditions 는 이루는 조건이다. 라운드가 닫힐 때 엔진이 보고 채워졌으면 성공으로 바꾼다(app/rounds/quest_goals.py).
         *     match 는 조건이 여럿일 때 모두(all) 채워야 하는지, 하나라도(any) 채우면 되는지다.
         *     조건이 없으면 성공하지 않는다. 사람(방장, 장부 초안)은 퀘스트를 성공으로 바꾸지 못한다.
         *     reveal 은 숨긴 퀘스트가 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 엔진이 보고 드러낸다.
         *     숨긴 채로 시작하는 퀘스트에만 적는다. 다른 퀘스트를 보는 조건(퀘스트 잇기)은 여기와 실패하는 조건에 쓴다.
         *     자기 자신을 보면 거부한다. 드러나는 조건이 없는 숨긴 퀘스트는 이루어야만 드러난다(드러내며 바로 성공).
         *     사람(방장, 장부 초안)은 퀘스트를 드러내지 못한다.
         *     fail 은 실패하는 조건, fail_match 는 그것을 맞추는 법이다(#367).
         *     진행 중인 퀘스트의 조건이 채워지면 엔진이 실패로 바꾼다.
         *     같은 라운드에 이루는 조건도 채워졌으면 성공이 먼저다. 물건을 잃는 것(lose_item)은 여기에만 쓴다.
         *     조건이 없으면 기한으로만 실패한다. 사람(방장)은 퀘스트를 실패로 바꾸지 못한다.
         *     규칙이 없는 사건 항목은 숨긴 채로 시작하고 보상과 기한과 조건이 없다.
         *     가리키는 사건과 보상의 물건이 붙인 로어북에 있는지는 게시할 때 본다.
         */
        "QuestRule-Output": {
            /**
             * Conditions
             * @default []
             */
            conditions: components["schemas"]["QuestCondition-Output"][];
            /** Entry Id */
            entry_id: string;
            /**
             * Fail
             * @default []
             */
            fail: components["schemas"]["QuestCondition-Output"][];
            /** @default all */
            fail_match: components["schemas"]["QuestMatch"];
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /**
             * Reveal
             * @default []
             */
            reveal: components["schemas"]["QuestCondition-Output"][];
            /** @default all */
            reveal_match: components["schemas"]["QuestMatch"];
            /**
             * Reward
             * @default []
             */
            reward: components["schemas"]["ItemStack-Output"][];
            /**
             * Reward Money
             * @default 0
             */
            reward_money: number;
            /** @default hidden */
            start: components["schemas"]["QuestStart"];
            /** Time Limit Minutes */
            time_limit_minutes?: number | null;
        };
        /**
         * QuestRuleSnapshot
         * @description 퀘스트 규칙 하나. 판 안의 로어북 사건 항목 하나(entry_id)가 퀘스트로서 어떤지다.
         *
         *     start 는 테이블이 시작할 때의 상태, reward 는 성공했을 때 받는 판 안의 물건, reward_money 는 받는 돈이다.
         *     time_limit_minutes 는 드러난 때부터 세는 기한(분)이다. 비어 있으면 기한이 없다.
         *     conditions 는 이루는 조건, match 는 그것을 모두 채워야 하는지 하나라도 되는지다. 조건이 없으면 성공하지 않는다.
         *     reveal 은 숨긴 퀘스트가 드러나는 조건, reveal_match 는 그것을 맞추는 법이다. 없으면 이루어야만 드러난다.
         *     fail 은 실패하는 조건, fail_match 는 그것을 맞추는 법이다. 없으면 기한으로만 실패한다.
         */
        QuestRuleSnapshot: {
            /**
             * Conditions
             * @default []
             */
            conditions: components["schemas"]["QuestConditionSnapshot"][];
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Fail
             * @default []
             */
            fail: components["schemas"]["QuestConditionSnapshot"][];
            /** @default all */
            fail_match: components["schemas"]["QuestMatch"];
            /** @default all */
            match: components["schemas"]["QuestMatch"];
            /**
             * Reveal
             * @default []
             */
            reveal: components["schemas"]["QuestConditionSnapshot"][];
            /** @default all */
            reveal_match: components["schemas"]["QuestMatch"];
            /**
             * Reward
             * @default []
             */
            reward: components["schemas"]["ItemStackSnapshot"][];
            /**
             * Reward Money
             * @default 0
             */
            reward_money: number;
            /** @default hidden */
            start: components["schemas"]["QuestStart"];
            /** Time Limit Minutes */
            time_limit_minutes?: number | null;
        };
        /**
         * QuestStart
         * @description 퀘스트가 테이블이 시작할 때 어떤 상태인가.
         *
         *     규칙을 적지 않은 사건 항목은 숨긴 채로 시작한다. 드러나는 조건이 없어서 드러나지 않는다.
         * @enum {string}
         */
        QuestStart: "hidden" | "active";
        /**
         * QuestStatus
         * @description 퀘스트의 상태. 테이블 전체가 함께 갖는다.
         *
         *     숨김 → 진행 중 → 성공 또는 실패. 숨긴 것을 바로 끝낼 수도 있다(몰래 이룬 일).
         *     끝난 것(성공, 실패)은 되돌리지 않는다. 진행 중인 것을 다시 숨기지 않는다. 바꾸는 규칙은 app/tables/quests.py 다.
         * @enum {string}
         */
        QuestStatus: "hidden" | "active" | "succeeded" | "failed";
        /**
         * Rating
         * @description 이용 등급.
         * @enum {string}
         */
        Rating: "all" | "adult";
        /**
         * RecommendedPlayers
         * @description 추천 인원. 최소와 최대를 함께 보낸다.
         *
         *     추천일 뿐이다. 테이블의 정원을 막지 않는다. 혼자서도, 넷이서도 할 수 있다.
         */
        RecommendedPlayers: {
            /** Max */
            max: number;
            /** Min */
            min: number;
        };
        /**
         * ReferenceCopy
         * @description 복사할 줄들. 고른 차례대로 넣는다.
         */
        ReferenceCopy: {
            /** Reference Ids */
            reference_ids: string[];
        };
        /**
         * ReferenceItem
         * @description 참고 자료 한 줄. 고르는 화면이 보인다.
         *
         *     name 과 content 는 보이는 것(한국어로 옮긴 것, 없으면 원본)이다. original_name 은 원본의 이름이다.
         *     원본의 수치(data)는 싣지 않는다.
         */
        ReferenceItem: {
            /** Content */
            content: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Key */
            key: string;
            kind: components["schemas"]["ReferenceKind"];
            /** Name */
            name: string;
            /** Original Name */
            original_name: string;
            /** Source */
            source: string;
        };
        /**
         * ReferenceKind
         * @description 참고 자료 한 줄의 종류. 서술의 프롬프트가 종류를 붙여 보인다.
         * @enum {string}
         */
        ReferenceKind: "monster" | "item";
        /**
         * ReferencePage
         * @description 찾은 줄들의 한 쪽.
         *
         *     attributions 는 이 쪽의 줄들이 나온 자료의 출처 표시다. 화면이 함께 보인다(SRD 5.1 은 CC BY 4.0 이다).
         */
        ReferencePage: {
            /** Attributions */
            attributions: string[];
            /** Items */
            items: components["schemas"]["ReferenceItem"][];
            /** Total */
            total: number;
        };
        /**
         * ReferencesUpdate
         * @description 참고 자료를 서술에 넣을지 바꿀 때 받는 값. 칸을 빼먹으면 거부한다.
         */
        ReferencesUpdate: {
            /** References Enabled */
            references_enabled: boolean;
        };
        /**
         * RepairAction
         * @description 지금 서 있는 장소에 닿은 길의 부서진 문을 고치는 행동(#281). 판에 적힌 고치는 판정(능력, 난이도)으로 굴린다.
         *
         *     판이 도구를 요구하면 고치기를 거드는 물건(item)을 붙여야 고친다(#802). 성공하면 문이 고쳐져 다시 잠글 수 있다.
         *     고친 문은 열린 채다. 지나가지는 않는다.
         */
        RepairAction: {
            /** Item */
            item?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "repair";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * RepairCheck
         * @description 부서진 문을 고치는 판정(#281). 행동 '고치기'가 이 능력과 난이도로 굴린다. 적지 않으면 고치지 못한다.
         *
         *     성공하면 문이 고쳐진다. 고친 문은 열린 채다. 다시 잠그려면 잠그기를 한다.
         *     needs_tool 이면 고치기를 거드는 물건(공구 같은 것)이 있어야 고친다(#802). 따기와 같다.
         */
        RepairCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Needs Tool
             * @default false
             */
            needs_tool: boolean;
        };
        /**
         * RepairRouteEffect
         * @description 사건의 효과 하나: 길 하나의 부서진 문을 고친다(repair_route, #281).
         *
         *     고친 문은 열린 채다. 다시 잠그려면 뒤에 잠그는 효과(lock_route)를 잇는다. 부서지지 않은 문은 그대로다.
         */
        "RepairRouteEffect-Input": {
            /**
             * From Place
             * Format: uuid
             */
            from_place: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "repair_route";
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
        };
        /**
         * RepairRouteEffect
         * @description 사건의 효과 하나: 길 하나의 부서진 문을 고친다(repair_route, #281).
         *
         *     고친 문은 열린 채다. 다시 잠그려면 뒤에 잠그는 효과(lock_route)를 잇는다. 부서지지 않은 문은 그대로다.
         */
        "RepairRouteEffect-Output": {
            /** From Place */
            from_place: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "repair_route";
            /** To Place */
            to_place: string;
        };
        /**
         * RepairSnapshot
         * @description 부서진 문을 고치는 판정(#281). 능력치, 난이도의 이름과 있어야 하는 도구(판 안의 물건 항목, 없으면 None).
         */
        RepairSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Needs Tool
             * @default false
             */
            needs_tool: boolean;
        };
        /**
         * ReplaceAction
         * @description 지금 서 있는 장소에 닿은 길의 문의 자물쇠를 바꿔 다는 행동(#281). 굴리지 않는다.
         *
         *     item 은 지닌 자물쇠 물건(판에 자물쇠를 적은 물건 항목)이다. 판에 자물쇠가 있던 문에만 단다.
         *     부서진 문은 고친 뒤에, 잠긴 자물쇠는 연 뒤에 바꾼다. 단 자물쇠는 열린 채이고, 그 자물쇠 물건의 열쇠로만 잠그고 연다.
         *     자물쇠 물건은 소지품에서 하나 없어진다. 한 테이블에서 자물쇠 물건 하나는 한 번만 단다. 지나가지는 않는다.
         */
        ReplaceAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "replace";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * ResistLevel
         * @description 저항의 단계(#886 ②). 그 성질의 해로운 것을 얼마나 받는가.
         * @enum {string}
         */
        ResistLevel: "resist" | "immune" | "vulnerable";
        /**
         * Resistance
         * @description 저항 한 줄(#886 ②). 성질(nature, 규칙의 natures 의 이름표)과 그 단계(level)다.
         *
         *     캐릭터와 NPC 의 시트, 착용한 장비의 아이템 규칙, 부상(상태)의 정의에 단다. 입고 있는 동안 저항이 생긴다.
         */
        Resistance: {
            level: components["schemas"]["ResistLevel"];
            /** Nature */
            nature: string;
        };
        /**
         * Resource
         * @description HP 말고 캐릭터가 가지는 수치 하나(#804). 마나, 스태미나, 광기, 피로 같은 것이다.
         *
         *     key 는 효과(adjust)와 시트가 가리키는 이름표, name 은 보이는 이름이다.
         *     min 이 바닥이고, 최대는 max 가 정한다(능력치에서 올 수 있다). start 가 시트를 받을 때의 값이다.
         *     rest 는 짧은 휴식과 긴 휴식이 이 수치에 하는 일이다. 값은 엔진만 바꾼다(쉬기, 물건의 adjust).
         *     each_round 는 라운드가 닫힐 때마다 저절로 하는 일이다(#804, 광기 +1, 마나 +1). 없으면 저절로 바뀌지 않는다.
         *     at_min 과 at_max 는 문턱이다(#804). 값이 최소(최대)에 닿아 있는 동안 그 부상(규칙의 injuries 의 key)을 입는다.
         *     문턱을 벗어나면 바로 풀린다. 부상은 수치의 그림자다(app/rounds/resource_rounds.py).
         *     visibility 는 누가 숫자를 보나다(#804). 비우면 모두다.
         *     holders 는 누가 이 수치를 가지나다(#804, 캐릭터·NPC·몬스터). 비우면 캐릭터만이다. 최대는 각자의 능력치로 정한다.
         */
        Resource: {
            /** At Max */
            at_max?: string | null;
            /** At Min */
            at_min?: string | null;
            each_round?: components["schemas"]["ResourceShift"] | null;
            /**
             * Holders
             * @default [
             *       "characters"
             *     ]
             */
            holders: components["schemas"]["ResourceHolder"][];
            /** Key */
            key: string;
            max: components["schemas"]["ResourceMax"];
            /**
             * Min
             * @default 0
             */
            min: number;
            /** Name */
            name: string;
            /** @default {} */
            rest: components["schemas"]["ResourceRest"];
            /** @default max */
            start: components["schemas"]["ResourceStart"];
            /** @default everyone */
            visibility: components["schemas"]["ResourceVisibility"];
        };
        /**
         * ResourceHolder
         * @description 수치를 누가 가지나(#804). 수치마다 하나 이상이다.
         * @enum {string}
         */
        ResourceHolder: "characters" | "npcs" | "monsters";
        /**
         * ResourceMax
         * @description 수치의 최대. base 에 능력치(ability)의 보정을 더하고, cap 이 있으면 그것을 넘지 않는다.
         *
         *     능력치를 비우면 base 그대로다(고정값). 플레이어가 능력치를 정한 캐릭터의 최대 HP 와 같은 식이다.
         *     보정이 음수라 최소보다 작아지면 최소다.
         */
        ResourceMax: {
            /** Ability */
            ability?: string | null;
            /** Base */
            base: number;
            /** Cap */
            cap?: number | null;
        };
        /**
         * ResourceOut
         * @description 시트의 수치 하나(#804). 마나, 스태미나 같은 것이다. 규칙의 수치(rules.resources)의 차례로 나온다.
         *
         *     최대는 그 캐릭터의 능력치로 정해진 값이다. 값은 늘 min 과 max 사이다.
         */
        ResourceOut: {
            /** Key */
            key: string;
            /** Max */
            max: number;
            /** Min */
            min: number;
            /** Name */
            name: string;
            /** Value */
            value: number;
        };
        /**
         * ResourceRest
         * @description 수치가 쉬기에 따라 바뀌는 것. 비우면 그 휴식은 이 수치를 바꾸지 않는다.
         */
        ResourceRest: {
            long?: components["schemas"]["ResourceShift"] | null;
            short?: components["schemas"]["ResourceShift"] | null;
        };
        /**
         * ResourceShift
         * @description 쉬기 하나나 라운드 하나가 수치에 하는 일. 올리기와 내리기에만 양(amount)이 있다. 범위 밖으로는 가지 않는다.
         */
        ResourceShift: {
            /** Amount */
            amount?: number | null;
            kind: components["schemas"]["ResourceShiftKind"];
        };
        /**
         * ResourceShiftKind
         * @description 쉬기가 수치에 하는 일(#804).
         * @enum {string}
         */
        ResourceShiftKind: "raise" | "lower" | "fill" | "empty";
        /**
         * ResourceShiftOut
         * @description 수치 하나가 바뀐 것(#804). 쉬기나 물건의 맞추기가 바꿨다. 이름표와 이름, 바뀌기 전과 뒤의 값, 그 캐릭터의 최대다.
         */
        ResourceShiftOut: {
            /** After */
            after: number;
            /** Before */
            before: number;
            /** Max */
            max: number;
            /** Name */
            name: string;
            /** Resource */
            resource: string;
        };
        /**
         * ResourceStart
         * @description 수치의 시작 값(#804). 시트를 받을 때 이 값으로 둔다.
         * @enum {string}
         */
        ResourceStart: "max" | "min";
        /**
         * ResourceVisibility
         * @description 수치를 누가 보나(#804). 방장도 이 규칙대로만 본다. 숨긴 수치도 서술자에게는 말(네 단계)로 간다.
         * @enum {string}
         */
        ResourceVisibility: "everyone" | "owner" | "engine";
        /**
         * Rest
         * @description 쉬기. 짧은 휴식과 긴 휴식, 되살아나기, 저절로 회복하기다.
         *
         *     쉬는 것은 캐릭터가 선언하는 행동이다(app/rounds/rests.py). 쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다.
         *     revive 가 None 이면 쓰러진 캐릭터는 쉬어서 일어나지 못한다(치료나 회복으로만 일어난다).
         *     natural 이 None 이면 쉬지 않고는 회복하지 않는다.
         */
        Rest: {
            long: components["schemas"]["LongRest"];
            natural: components["schemas"]["NaturalRecovery"] | null;
            revive: components["schemas"]["Revive"] | null;
            short: components["schemas"]["ShortRest"];
        };
        /**
         * RestAction
         * @description 쉬는 행동(app/rounds/rests.py). 얼마나 쉬는지(length)만 받는다. 시간과 회복량은 규칙이 정한다.
         *
         *     쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다. 그동안 다치면 휴식이 깨져 회복하지 않는다.
         */
        RestAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "rest";
            length: components["schemas"]["RestLength"];
        };
        /**
         * RestLength
         * @description 휴식의 길이. 규칙의 Rest.short, Rest.long 에 맞춘다.
         * @enum {string}
         */
        RestLength: "short" | "long";
        /**
         * RestOut
         * @description 쉰 결과. 엔진이 정했다(app/rounds/rests.py). 판정이 없다.
         *
         *     쉬는 라운드는 적어도 그 휴식의 시간만큼 이어진다. 그 라운드에 다쳤거나 쓰러졌거나 죽었으면 휴식이 깨져
         *     회복하지 않는다(rested 가 false, reason 이 hurt, downed, dead, ambushed(무작위 조우의 몬스터가 덮쳤다, #283)).
         */
        RestOut: {
            /** After */
            after: number;
            /** Before */
            before: number;
            /** Length */
            length: string;
            /** Max Hp */
            max_hp: number;
            /** Minutes */
            minutes: number;
            /** Reason */
            reason: string | null;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /** Rested */
            rested: boolean;
            /** Rolls */
            rolls: number[];
        };
        /**
         * RestOutcome
         * @description 쉬는 행동의 결과.
         */
        RestOutcome: {
            rest: components["schemas"]["RestOut"];
        };
        /**
         * Revive
         * @description 되살아나기. 고비를 넘기고(죽음의 굴림의 성공이 다 모여) 쓰러져 있는 캐릭터가 쉬어서 일어나는 법이다.
         *
         *     한 장면에 minutes 분이 흐르면 규칙의 주사위(Ruleset.die)를 한 번 굴린다. 능력치의 보정은 더하지 않는다.
         *     눈이 target 이상이면 HP 1 로 일어난다. 아니면 쓰러진 채로 있고, 다음에 그만큼 흐르면 다시 굴린다.
         *     죽음의 굴림과 다르다. 그것은 죽어 가는 캐릭터가 죽는지를 정하고, 이것은 고비를 넘긴 캐릭터가 일어나는지를 정한다.
         */
        Revive: {
            /** Minutes */
            minutes: number;
            /** Target */
            target: number;
        };
        /**
         * RobbedWake
         * @description 쓰러져 있는 동안 물건을 빼앗긴 NPC 가 깨어날 때의 반응(#494). 백면체를 한 번 굴려 정한다.
         *
         *     hostile(%) 이하면 적대, 그다음 wary(%) 만큼이면 경계, 나머지는 눈치채지 못한다. 둘의 합은 100 을 넘지 않는다.
         */
        RobbedWake: {
            /** Hostile */
            hostile: number;
            /** Wary */
            wary: number;
        };
        /**
         * RollOut
         * @description 주사위로 굴린 능력치의 점수들. 앉은 사람은 서로의 굴림을 본다.
         */
        RollOut: {
            /** Character Number */
            character_number: number;
            /** Dice */
            dice: number[][];
            /** Reroll Granted */
            reroll_granted: boolean;
            /** Scores */
            scores: number[];
            /** Times Rolled */
            times_rolled: number;
        };
        /**
         * RolledOut
         * @description 굴린 판정 하나. 엔진이 정했다(app/engine/check.py 의 Check).
         */
        RolledOut: {
            /** Modifier */
            modifier: number;
            /** Roll */
            roll: number;
            /** Success */
            success: boolean;
            /** Target */
            target: number;
            /** Total */
            total: number;
        };
        /**
         * RoundOut
         * @description 앉은 사람이 라운드를 볼 때의 값.
         */
        RoundOut: {
            /** Arrivals */
            arrivals: components["schemas"]["ArrivalOut"][];
            /** Closed At */
            closed_at: string | null;
            /** Closing At */
            closing_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Deadline At */
            deadline_at: string | null;
            /** Death Saves */
            death_saves: components["schemas"]["DeathSaveOut"][];
            /** Declarations */
            declarations: components["schemas"]["DeclarationOut"][];
            /** Input Step */
            input_step: number;
            /** Narration Failed At */
            narration_failed_at: string | null;
            /** Narration Failures */
            narration_failures: number;
            /** Narration Model */
            narration_model: string | null;
            /** Number */
            number: number;
            /** Output Step */
            output_step: number;
            price: components["schemas"]["RoundPriceOut"] | null;
            /** Scene */
            scene: string;
            status: components["schemas"]["RoundStatus"];
            /** Waiting For */
            waiting_for: string[];
        };
        /**
         * RoundPage
         * @description 라운드 목록의 한 쪽.
         */
        RoundPage: {
            /** Items */
            items: components["schemas"]["RoundOut"][];
            /** Total */
            total: number;
        };
        /**
         * RoundPriceOut
         * @description 라운드에 알린 1인 1라운드의 값. credits 는 결제 서버가 정한 값(글자)이고 tier 가 premium 이면 골드로만 낸다.
         */
        RoundPriceOut: {
            /** Credits */
            credits: string;
            /** Tier */
            tier: string | null;
        };
        /**
         * RoundStatus
         * @description 라운드의 상태. 한 방향으로만 나아간다.
         * @enum {string}
         */
        RoundStatus: "open" | "closing" | "closed";
        /**
         * RoundTimeLimitUpdate
         * @description 라운드의 시간 제한을 바꿀 때 받는 값. null 이면 시간 제한을 없앤다. 칸을 빼먹으면 거부한다.
         */
        RoundTimeLimitUpdate: {
            /** Round Time Limit */
            round_time_limit: number | null;
        };
        /**
         * RouteBar
         * @description 길의 빗장(#281). 길의 한쪽 끝(side)에만 있다. 그쪽에 선 사람만 열쇠 없이 걸고 푼다(행동 '잠그기', '열기').
         *
         *     걸려 있으면 빗장 쪽에서는 지나가며 풀고, 반대쪽에서는 지나가지 못한다. 반대쪽에서는 부수기로만 연다.
         *     barred 는 테이블이 시작할 때 걸려 있는가다(기본은 안 걸림). side 는 길의 두 끝 중 하나여야 한다.
         */
        "RouteBar-Input": {
            /**
             * Barred
             * @default false
             */
            barred: boolean;
            /**
             * Side
             * Format: uuid
             */
            side: string;
        };
        /**
         * RouteBar
         * @description 길의 빗장(#281). 길의 한쪽 끝(side)에만 있다. 그쪽에 선 사람만 열쇠 없이 걸고 푼다(행동 '잠그기', '열기').
         *
         *     걸려 있으면 빗장 쪽에서는 지나가며 풀고, 반대쪽에서는 지나가지 못한다. 반대쪽에서는 부수기로만 연다.
         *     barred 는 테이블이 시작할 때 걸려 있는가다(기본은 안 걸림). side 는 길의 두 끝 중 하나여야 한다.
         */
        "RouteBar-Output": {
            /**
             * Barred
             * @default false
             */
            barred: boolean;
            /** Side */
            side: string;
        };
        /**
         * RouteCrossOut
         * @description 길에 적힌 판정 하나(#281). 넘기(지날 때마다 가는 사람이 굴린다), 따기, 부수기, 고치기다.
         *
         *     룰북의 능력치와 난이도의 이름표다.
         */
        RouteCrossOut: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string;
        };
        /**
         * RouteDoorEffect
         * @description 사건의 효과 하나: 길 하나의 문을 잠그거나(lock_route) 연다(unlock_route, #281).
         *
         *     판이 하는 일이라 열쇠도 서 있는 쪽도 보지 않는다. NPC 나 몬스터가 문을 잠그고 여는 것을 이것으로 적는다.
         *     device 를 적으면 그 장치만, 비우면 그 문의 장치 모두(자물쇠, 빗장)다. 적은 장치가 그 길에 있는지는 게시할 때 본다.
         *     부서진 문은 잠그지 못한다(고치는 효과를 먼저 적는다). 이미 그렇게 되어 있는 장치는 그대로다.
         */
        "RouteDoorEffect-Input": {
            device?: components["schemas"]["DoorDevice"] | null;
            /**
             * From Place
             * Format: uuid
             */
            from_place: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "lock_route" | "unlock_route";
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
        };
        /**
         * RouteDoorEffect
         * @description 사건의 효과 하나: 길 하나의 문을 잠그거나(lock_route) 연다(unlock_route, #281).
         *
         *     판이 하는 일이라 열쇠도 서 있는 쪽도 보지 않는다. NPC 나 몬스터가 문을 잠그고 여는 것을 이것으로 적는다.
         *     device 를 적으면 그 장치만, 비우면 그 문의 장치 모두(자물쇠, 빗장)다. 적은 장치가 그 길에 있는지는 게시할 때 본다.
         *     부서진 문은 잠그지 못한다(고치는 효과를 먼저 적는다). 이미 그렇게 되어 있는 장치는 그대로다.
         */
        "RouteDoorEffect-Output": {
            device?: components["schemas"]["DoorDevice"] | null;
            /** From Place */
            from_place: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "lock_route" | "unlock_route";
            /** To Place */
            to_place: string;
        };
        /**
         * RouteLock
         * @description 길의 자물쇠(#281). 잠겨 있으면 그 열쇠(key)를 지닌 사람만 지나간다. 지나가면서 연다.
         *
         *     열쇠는 붙인 로어북의 물건 항목 하나다. 열쇠 하나는 자물쇠 하나만 연다. 같은 열쇠를 두 길에 적으면 게시하지 못한다.
         *     locked 는 테이블이 시작할 때 잠겨 있는가다(기본은 잠김). 연 문은 누가 다시 잠그기 전까지 열린 채다.
         *     열쇠를 지닌 사람은 길의 어느 끝에서든 잠그고 연다(행동 '잠그기', '열기'). 열쇠는 쓰여도 없어지지 않는다.
         *     pick 을 적었으면 열쇠 없이 따기로 열 수 있다. 적지 않으면 따지 못한다.
         */
        "RouteLock-Input": {
            /**
             * Key
             * Format: uuid
             */
            key: string;
            /**
             * Locked
             * @default true
             */
            locked: boolean;
            pick?: components["schemas"]["PickCheck"] | null;
        };
        /**
         * RouteLock
         * @description 길의 자물쇠(#281). 잠겨 있으면 그 열쇠(key)를 지닌 사람만 지나간다. 지나가면서 연다.
         *
         *     열쇠는 붙인 로어북의 물건 항목 하나다. 열쇠 하나는 자물쇠 하나만 연다. 같은 열쇠를 두 길에 적으면 게시하지 못한다.
         *     locked 는 테이블이 시작할 때 잠겨 있는가다(기본은 잠김). 연 문은 누가 다시 잠그기 전까지 열린 채다.
         *     열쇠를 지닌 사람은 길의 어느 끝에서든 잠그고 연다(행동 '잠그기', '열기'). 열쇠는 쓰여도 없어지지 않는다.
         *     pick 을 적었으면 열쇠 없이 따기로 열 수 있다. 적지 않으면 따지 못한다.
         */
        "RouteLock-Output": {
            /** Key */
            key: string;
            /**
             * Locked
             * @default true
             */
            locked: boolean;
            pick?: components["schemas"]["PickCheck"] | null;
        };
        /**
         * RouteOpenOut
         * @description 길의 문을 따거나 고치는 판정(#281). 넘기와 부수기의 것에 도구가 있어야 하는가(#802)가 더 있다.
         */
        RouteOpenOut: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string;
            /**
             * Needs Tool
             * @default false
             */
            needs_tool: boolean;
        };
        /**
         * RouteOut
         * @description 아는 길 하나. two_way 가 아니면 from_place 에서 to_place 로만 간다.
         *
         *     길의 조건(#281)도 싣는다. 잠긴 문과 오를 절벽은 보이는 것이다. 도구가 있어야 하는지(#802)도 보인다.
         *     무슨 열쇠로 여는지, 실패의 피해는 싣지 않는다.
         */
        RouteOut: {
            /** Bar Side */
            bar_side?: string | null;
            /** Barred */
            barred?: boolean | null;
            /**
             * Broken
             * @default false
             */
            broken: boolean;
            cross?: components["schemas"]["RouteCrossOut"] | null;
            force?: components["schemas"]["RouteCrossOut"] | null;
            /**
             * From Place
             * Format: uuid
             */
            from_place: string;
            /** Locked */
            locked?: boolean | null;
            pick?: components["schemas"]["RouteOpenOut"] | null;
            repair?: components["schemas"]["RouteOpenOut"] | null;
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
            /** Travel Minutes */
            travel_minutes?: number | null;
            /** Two Way */
            two_way: boolean;
        };
        /**
         * RouteRule
         * @description 길 하나. 붙인 로어북의 장소 항목 둘(from_place, to_place)을 잇는다.
         *
         *     two_way 면 양쪽으로 다닌다(기본). 아니면 from 에서 to 로만 간다(떨어지는 구멍, 한쪽에서만 열리는 문).
         *     visibility 는 플레이어가 길을 언제 아는가다(기본은 처음부터, RouteVisibility).
         *     숨긴 길(hidden)은 플레이어도 방장도 모른다. 숨긴 길에는 찾는 판정(find)이 있어야 하고, 다른 길에는 없다.
         *     travel_minutes 는 이 길로 한 칸 가는 데 걸리는 게임 안의 시간(분)이다. 양쪽이 같다. 비우면 라운드의 걸음 안에서 간다
         *     (옆방). 누가 이 길로 가면 다음 라운드가 열릴 때 그만큼은 흐른다(app/calendar/state.py 의 stretch_next_step).
         *     길의 조건(#281): cross 는 지날 때마다 굴리는 넘기 판정, lock 은 열쇠로 여는 자물쇠, bar 는 한쪽의 빗장,
         *     force 는 문(자물쇠와 빗장)을 부수는 판정, repair 는 부서진 문을 고치는 판정이다. 자물쇠와 넘기는 양쪽에서 같다.
         *     빗장, 자물쇠, 넘기 판정의 차례로 본다. force 와 repair 는 자물쇠나 빗장이 있는 길에만 적는다.
         *     가리키는 장소가 붙인 로어북에 있는지, 장소인지는 게시할 때 본다.
         */
        "RouteRule-Input": {
            bar?: components["schemas"]["RouteBar-Input"] | null;
            cross?: components["schemas"]["CrossCheck"] | null;
            find?: components["schemas"]["FindCheck"] | null;
            force?: components["schemas"]["ForceCheck"] | null;
            /**
             * From Place
             * Format: uuid
             */
            from_place: string;
            lock?: components["schemas"]["RouteLock-Input"] | null;
            repair?: components["schemas"]["RepairCheck"] | null;
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
            /** Travel Minutes */
            travel_minutes?: number | null;
            /**
             * Two Way
             * @default true
             */
            two_way: boolean;
            /** @default open */
            visibility: components["schemas"]["RouteVisibility"];
        };
        /**
         * RouteRule
         * @description 길 하나. 붙인 로어북의 장소 항목 둘(from_place, to_place)을 잇는다.
         *
         *     two_way 면 양쪽으로 다닌다(기본). 아니면 from 에서 to 로만 간다(떨어지는 구멍, 한쪽에서만 열리는 문).
         *     visibility 는 플레이어가 길을 언제 아는가다(기본은 처음부터, RouteVisibility).
         *     숨긴 길(hidden)은 플레이어도 방장도 모른다. 숨긴 길에는 찾는 판정(find)이 있어야 하고, 다른 길에는 없다.
         *     travel_minutes 는 이 길로 한 칸 가는 데 걸리는 게임 안의 시간(분)이다. 양쪽이 같다. 비우면 라운드의 걸음 안에서 간다
         *     (옆방). 누가 이 길로 가면 다음 라운드가 열릴 때 그만큼은 흐른다(app/calendar/state.py 의 stretch_next_step).
         *     길의 조건(#281): cross 는 지날 때마다 굴리는 넘기 판정, lock 은 열쇠로 여는 자물쇠, bar 는 한쪽의 빗장,
         *     force 는 문(자물쇠와 빗장)을 부수는 판정, repair 는 부서진 문을 고치는 판정이다. 자물쇠와 넘기는 양쪽에서 같다.
         *     빗장, 자물쇠, 넘기 판정의 차례로 본다. force 와 repair 는 자물쇠나 빗장이 있는 길에만 적는다.
         *     가리키는 장소가 붙인 로어북에 있는지, 장소인지는 게시할 때 본다.
         */
        "RouteRule-Output": {
            bar?: components["schemas"]["RouteBar-Output"] | null;
            cross?: components["schemas"]["CrossCheck"] | null;
            find?: components["schemas"]["FindCheck"] | null;
            force?: components["schemas"]["ForceCheck"] | null;
            /** From Place */
            from_place: string;
            lock?: components["schemas"]["RouteLock-Output"] | null;
            repair?: components["schemas"]["RepairCheck"] | null;
            /** To Place */
            to_place: string;
            /** Travel Minutes */
            travel_minutes?: number | null;
            /**
             * Two Way
             * @default true
             */
            two_way: boolean;
            /** @default open */
            visibility: components["schemas"]["RouteVisibility"];
        };
        /**
         * RouteSnapshot
         * @description 길 하나. 판 안의 로어북 장소 항목 둘을 잇는다.
         *
         *     two_way 가 아니면 from_place 에서 to_place 로만 간다. visibility 는 플레이어가 길을 언제 아는가다.
         *     숨긴 길은 찾는 판정(find)으로 드러난다. travel_minutes 는 한 칸 가는 데 걸리는 게임 안의 시간(분)이다.
         *     비어 있으면 라운드의 걸음 안에서 간다. 형식 26 보다 옛 판은 모두 비어 있다.
         *     cross 는 지날 때마다 굴리는 넘기 판정, lock 은 열쇠의 자물쇠다(#281). 형식 52 보다 옛 판은 둘 다 없다.
         *     bar 는 한쪽의 빗장, force 는 문을 부수는 판정이다. 형식 53 보다 옛 판은 둘 다 없고 자물쇠를 따지 못한다.
         *     repair 는 부서진 문을 고치는 판정이다. 형식 55 보다 옛 판은 없다(고치지 못한다).
         */
        RouteSnapshot: {
            bar?: components["schemas"]["BarSnapshot"] | null;
            cross?: components["schemas"]["CrossSnapshot"] | null;
            find?: components["schemas"]["FindSnapshot"] | null;
            force?: components["schemas"]["ForceSnapshot"] | null;
            /**
             * From Place
             * Format: uuid
             */
            from_place: string;
            lock?: components["schemas"]["LockSnapshot"] | null;
            repair?: components["schemas"]["RepairSnapshot"] | null;
            /**
             * To Place
             * Format: uuid
             */
            to_place: string;
            /** Travel Minutes */
            travel_minutes?: number | null;
            /**
             * Two Way
             * @default true
             */
            two_way: boolean;
            /** @default open */
            visibility: components["schemas"]["RouteVisibility"];
        };
        /**
         * RouteVisibility
         * @description 맵의 길을 플레이어가 언제 아는가. 제작자가 길마다 정한다.
         *
         *     아는 길의 두 끝은 아는 장소다. 길을 알면 어디로 가는지도 안다.
         *     숨긴 길은 방장도 모른다. 시나리오를 만든 사람과 AI GM 만 안다.
         * @enum {string}
         */
        RouteVisibility: "open" | "fog" | "hidden";
        /**
         * RulebookCreate
         * @description 룰북을 만들 때 받는 값. 제목만 필수다.
         *
         *     규칙을 직접 받지 않는다. 템플릿의 이름만 받고, 그 템플릿의 규칙을 서버가 채운다.
         *     방어 규칙(armor)만은 고를 수 있다(#276). 보내면 템플릿의 것 대신 쓴다. null 이면 방어구가 막지 않는 규칙이다.
         *     보내지 않으면 템플릿의 것이다. 수치(resources, #804)와 기술(skills, #805)도 같다. 보내면 템플릿의 예시 대신 쓴다.
         *     성질(natures)과 타입마다의 면역(monster_immunities, #886)도 같다. 부상(injuries)과 부상 표(injury_table, #886)도
         *     같다. 부상 표에 null 을 보내면 부상 표가 없는 규칙이다(그때는 굴리는 때 injury_triggers 를 모두 꺼야 한다).
         */
        RulebookCreate: {
            armor?: components["schemas"]["Armor"] | null;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Gm Guide
             * @default
             */
            gm_guide: string;
            /** Injuries */
            injuries?: components["schemas"]["Injury"][] | null;
            injury_table?: components["schemas"]["InjuryTable"] | null;
            injury_triggers?: components["schemas"]["InjuryTriggers"] | null;
            /** Monster Immunities */
            monster_immunities?: components["schemas"]["KindImmunity"][] | null;
            /** Natures */
            natures?: components["schemas"]["Nature"][] | null;
            /** Resources */
            resources?: components["schemas"]["Resource"][] | null;
            /** Skills */
            skills?: components["schemas"]["Skill"][] | null;
            /** @default srd5 */
            template: components["schemas"]["Template"];
            /** Title */
            title: string;
        };
        /**
         * RulebookDetail
         * @description 만든 사람이 자기 룰북을 볼 때의 값. 진행 지침과 규칙까지 싣는다.
         *
         *     진행 지침은 AI 만 보는 글이다. 만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는
         *     진행 지침이 없는 응답을 따로 만든다.
         */
        RulebookDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** Gm Guide */
            gm_guide: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            rules: components["schemas"]["Ruleset"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * RulebookSnapshot
         * @description 룰북. 진행 지침(AI 가 읽는 글)과 규칙(엔진이 실행하는 데이터)이다.
         */
        RulebookSnapshot: {
            /** Gm Guide */
            gm_guide: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            rules: components["schemas"]["Ruleset"];
            /** Title */
            title: string;
        };
        /**
         * RulebookUpdate
         * @description 룰북을 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     규칙은 방어 규칙(armor), 수치(resources, #804), 기술(skills, #805), 성질(natures)과 타입마다의 면역
         *     (monster_immunities, #886), 부상(injuries)과 부상 표(injury_table)와 굴리는 때(injury_triggers, #886)만
         *     고칠 수 있다.
         *     부상 표에 null 을 보내면 부상 표가 없는 규칙이 된다(굴리는 때를 모두 함께 꺼야 한다).
         *     방어 규칙에 null 을 보내면 방어구가 막지 않는 규칙이, 수치에 빈 목록을 보내면 HP 뿐인 규칙이 된다.
         *     이미 게시한 판은 그때의 규칙으로 굳어 있어 바뀌지 않는다. template 이나 rules 를 보내면 모르는 칸이라 거절한다.
         */
        RulebookUpdate: {
            armor?: components["schemas"]["Armor"] | null;
            /** Description */
            description?: string | null;
            /** Gm Guide */
            gm_guide?: string | null;
            /** Injuries */
            injuries?: components["schemas"]["Injury"][] | null;
            injury_table?: components["schemas"]["InjuryTable"] | null;
            injury_triggers?: components["schemas"]["InjuryTriggers"] | null;
            /** Monster Immunities */
            monster_immunities?: components["schemas"]["KindImmunity"][] | null;
            /** Natures */
            natures?: components["schemas"]["Nature"][] | null;
            /** Resources */
            resources?: components["schemas"]["Resource"][] | null;
            /** Skills */
            skills?: components["schemas"]["Skill"][] | null;
            /** Title */
            title?: string | null;
        };
        /**
         * Ruleset
         * @description 규칙 한 벌.
         *
         *     template 은 어느 템플릿에서 왔는지를 적어 둔 것이다(app/engine/templates/). 엔진은 이 값을 보지 않는다.
         *     narration(서술 지침)도 엔진은 보지 않는다. 서술자만 읽는다.
         */
        Ruleset: {
            /** Abilities */
            abilities: components["schemas"]["Ability"][];
            armor: components["schemas"]["Armor"] | null;
            called_shot: components["schemas"]["CalledShot"] | null;
            death_save: components["schemas"]["DeathSave"] | null;
            /** Default Difficulty */
            default_difficulty: string;
            /** Die */
            die: number;
            /** Difficulties */
            difficulties: components["schemas"]["Difficulty"][];
            /** Equipment Slots */
            equipment_slots: components["schemas"]["EquipmentSlot"][];
            /** Hp Ability */
            hp_ability: string | null;
            /** Initiative Ability */
            initiative_ability: string | null;
            /** Injuries */
            injuries: components["schemas"]["Injury"][];
            injury_table: components["schemas"]["InjuryTable"] | null;
            injury_triggers: components["schemas"]["InjuryTriggers"];
            item_check: components["schemas"]["ItemCheck"] | null;
            /** Magnitudes */
            magnitudes: components["schemas"]["Magnitude"][];
            modifier: components["schemas"]["Modifier"];
            /** Monster Immunities */
            monster_immunities: components["schemas"]["KindImmunity"][];
            narration: components["schemas"]["NarrationGuide"] | null;
            /** Natures */
            natures: components["schemas"]["Nature"][];
            point_buy: components["schemas"]["PointBuy"] | null;
            /** Resources */
            resources: components["schemas"]["Resource"][];
            rest: components["schemas"]["Rest"] | null;
            robbed_wake: components["schemas"]["RobbedWake"] | null;
            /** Score Max */
            score_max: number;
            /** Score Min */
            score_min: number;
            score_roll: components["schemas"]["ScoreRoll"] | null;
            /** Skills */
            skills: components["schemas"]["Skill"][];
            steal: components["schemas"]["Steal"] | null;
            /** Template */
            template: string;
            treatment: components["schemas"]["Treatment"] | null;
        };
        /**
         * SanctionOut
         * @description 시나리오를 제재한 결과.
         */
        SanctionOut: {
            /**
             * Owner Id
             * Format: uuid
             */
            owner_id: string;
            /** Publishing Banned */
            publishing_banned: boolean;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Version Number */
            version_number: number;
        };
        /**
         * SaveOut
         * @description 세이브 굴림(#276). kind 는 armor(그 부위의 방어), cover(엄폐한 장소의 커버), ward(불굴) 중 하나다.
         *     눈 + value 가 target 이상이면 막았다.
         */
        SaveOut: {
            /** Kind */
            kind: string;
            /** Roll */
            roll: number;
            /** Saved */
            saved: boolean;
            /** Target */
            target: number;
            /** Value */
            value: number;
        };
        /**
         * ScenarioCreate
         * @description 시나리오를 만들 때 받는 값. 제목만 필수다.
         *
         *     룰북과 스타팅 없이도 만들 수 있다(임시 저장). 게시할 때 둘 다 있는지 검사한다.
         *     시트도 비워 둘 수 있다. 게시할 때 룰북의 규칙과 견주어 검사한다.
         */
        ScenarioCreate: {
            /**
             * Bestiary Ids
             * @default []
             */
            bestiary_ids: string[];
            /**
             * Character Modes
             * @default [
             *       "pregen",
             *       "custom"
             *     ]
             */
            character_modes: components["schemas"]["CharacterMode"][];
            /**
             * @default {
             *       "round_minutes": 10,
             *       "start_day": 1,
             *       "start_hour": 8
             *     }
             */
            clock: components["schemas"]["Clock"];
            /**
             * Covers
             * @default []
             */
            covers: components["schemas"]["CoverRule-Input"][];
            currency?: components["schemas"]["Currency"] | null;
            default_npc_sheet?: components["schemas"]["Sheet"] | null;
            default_sheet?: components["schemas"]["CharacterSheet"] | null;
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Encounters
             * @default []
             */
            encounters: components["schemas"]["Encounter-Input"][];
            /**
             * Happenings
             * @default []
             */
            happenings: components["schemas"]["HappeningRule-Input"][];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemRule-Input"][];
            /**
             * Landmarks
             * @default []
             */
            landmarks: string[];
            /**
             * Lorebook Ids
             * @default []
             */
            lorebook_ids: string[];
            /**
             * Monster Sheets
             * @default []
             */
            monster_sheets: components["schemas"]["MonsterSheet-Input"][];
            /** Narration Model */
            narration_model: string;
            /** @default classic */
            narration_style: components["schemas"]["NarrationStyle"];
            /**
             * Npc Places
             * @default []
             */
            npc_places: components["schemas"]["NpcPlace-Input"][];
            /**
             * Npc Sheets
             * @default []
             */
            npc_sheets: components["schemas"]["NpcSheet-Input"][];
            /**
             * Openings
             * @default []
             */
            openings: string[];
            /**
             * Place Items
             * @default []
             */
            place_items: components["schemas"]["PlaceItem-Input"][];
            player_made_hp?: components["schemas"]["PlayerMadeHp"] | null;
            /**
             * Pregens
             * @default []
             */
            pregens: components["schemas"]["Pregen-Input"][];
            /**
             * Quests
             * @default []
             */
            quests: components["schemas"]["QuestRule-Input"][];
            /** @default all */
            rating: components["schemas"]["Rating"];
            /**
             * @default {
             *       "max": 4,
             *       "min": 1
             *     }
             */
            recommended_players: components["schemas"]["RecommendedPlayers"];
            /**
             * Reroll Allowed
             * @default false
             */
            reroll_allowed: boolean;
            /**
             * Routes
             * @default []
             */
            routes: components["schemas"]["RouteRule-Input"][];
            /** Rulebook Id */
            rulebook_id?: string | null;
            /** Start Place */
            start_place?: string | null;
            /**
             * Starting Items
             * @default []
             */
            starting_items: components["schemas"]["ItemStack-Input"][];
            /** Title */
            title: string;
            /**
             * Traps
             * @default []
             */
            traps: components["schemas"]["PlacedTrap-Input"][];
            /**
             * Wanders
             * @default []
             */
            wanders: components["schemas"]["WanderTable-Input"][];
            /** World Id */
            world_id?: string | null;
        };
        /**
         * ScenarioDetail
         * @description 만든 사람이 자기 시나리오를 볼 때의 값. 가리키는 자산은 ID 만 싣는다. 내용은 그 자산의 주소에서 읽는다.
         */
        ScenarioDetail: {
            /** Bestiary Ids */
            bestiary_ids: string[];
            /** Character Modes */
            character_modes: components["schemas"]["CharacterMode"][];
            clock: components["schemas"]["Clock"];
            /** Covers */
            covers: components["schemas"]["CoverRule-Output"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            currency: components["schemas"]["Currency"] | null;
            default_npc_sheet: components["schemas"]["Sheet"] | null;
            default_sheet: components["schemas"]["CharacterSheet"] | null;
            /** Description */
            description: string;
            /** Encounters */
            encounters: components["schemas"]["Encounter-Output"][];
            /** Happenings */
            happenings: components["schemas"]["HappeningRule-Output"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Items */
            items: components["schemas"]["ItemRule-Output"][];
            /** Landmarks */
            landmarks: string[];
            /** Lorebook Ids */
            lorebook_ids: string[];
            /** Monster Sheets */
            monster_sheets: components["schemas"]["MonsterSheet-Output"][];
            /** Narration Model */
            narration_model: string | null;
            narration_model_status: components["schemas"]["ModelStatusOut"] | null;
            narration_style: components["schemas"]["NarrationStyle"];
            /** Npc Places */
            npc_places: components["schemas"]["NpcPlace-Output"][];
            /** Npc Sheets */
            npc_sheets: components["schemas"]["NpcSheet-Output"][];
            /** Openings */
            openings: string[];
            /** Place Items */
            place_items: components["schemas"]["PlaceItem-Output"][];
            player_made_hp: components["schemas"]["PlayerMadeHp"] | null;
            /** Pregens */
            pregens: components["schemas"]["Pregen-Output"][];
            /** Quests */
            quests: components["schemas"]["QuestRule-Output"][];
            rating: components["schemas"]["Rating"];
            recommended_players: components["schemas"]["RecommendedPlayers"];
            /** Reroll Allowed */
            reroll_allowed: boolean;
            /** Routes */
            routes: components["schemas"]["RouteRule-Output"][];
            /** Rulebook Id */
            rulebook_id: string | null;
            /** Start Place */
            start_place: string | null;
            /** Starting Items */
            starting_items: components["schemas"]["ItemStack-Output"][];
            /** Title */
            title: string;
            /** Traps */
            traps: components["schemas"]["PlacedTrap-Output"][];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
            /** Wanders */
            wanders: components["schemas"]["WanderTable-Output"][];
            /** World Id */
            world_id: string | null;
        };
        /**
         * ScenarioPage
         * @description 시나리오 목록의 한 쪽.
         */
        ScenarioPage: {
            /** Items */
            items: components["schemas"]["ScenarioSummary"][];
            /** Total */
            total: number;
        };
        /**
         * ScenarioSummary
         * @description 시나리오의 목록에 싣는 값. 공통 값에 등급을 더한다. 목록에서 등급으로 가려 보여 줄 수 있어야 한다.
         */
        ScenarioSummary: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            rating: components["schemas"]["Rating"];
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * ScenarioUpdate
         * @description 시나리오를 고칠 때 받는 값. 보낸 칸만 바꾼다.
         *
         *     rulebook_id, world_id, default_sheet, default_npc_sheet, player_made_hp, start_place, currency 는
         *     null 을 보내면 비운다.
         *     보내지 않으면 그대로 둔다.
         *     lorebook_ids, bestiary_ids, openings, pregens, npc_sheets, monster_sheets, encounters, items, starting_items,
         *     quests, routes, landmarks, place_items, covers, traps, wanders, happenings, npc_places, character_modes 는
         *     보낸 목록으로 통째로 바꾼다.
         *     character_modes 말고는 전부 없애려면 빈 목록을 보낸다. character_modes 는 비울 수 없다.
         *     recommended_players 는 최소와 최대를 함께 보낸다. clock 은 셋을 함께 보낸다.
         */
        ScenarioUpdate: {
            /** Bestiary Ids */
            bestiary_ids?: string[] | null;
            /** Character Modes */
            character_modes?: components["schemas"]["CharacterMode"][] | null;
            clock?: components["schemas"]["Clock"] | null;
            /** Covers */
            covers?: components["schemas"]["CoverRule-Input"][] | null;
            currency?: components["schemas"]["Currency"] | null;
            default_npc_sheet?: components["schemas"]["Sheet"] | null;
            default_sheet?: components["schemas"]["CharacterSheet"] | null;
            /** Description */
            description?: string | null;
            /** Encounters */
            encounters?: components["schemas"]["Encounter-Input"][] | null;
            /** Happenings */
            happenings?: components["schemas"]["HappeningRule-Input"][] | null;
            /** Items */
            items?: components["schemas"]["ItemRule-Input"][] | null;
            /** Landmarks */
            landmarks?: string[] | null;
            /** Lorebook Ids */
            lorebook_ids?: string[] | null;
            /** Monster Sheets */
            monster_sheets?: components["schemas"]["MonsterSheet-Input"][] | null;
            /** Narration Model */
            narration_model?: string | null;
            narration_style?: components["schemas"]["NarrationStyle"] | null;
            /** Npc Places */
            npc_places?: components["schemas"]["NpcPlace-Input"][] | null;
            /** Npc Sheets */
            npc_sheets?: components["schemas"]["NpcSheet-Input"][] | null;
            /** Openings */
            openings?: string[] | null;
            /** Place Items */
            place_items?: components["schemas"]["PlaceItem-Input"][] | null;
            player_made_hp?: components["schemas"]["PlayerMadeHp"] | null;
            /** Pregens */
            pregens?: components["schemas"]["Pregen-Input"][] | null;
            /** Quests */
            quests?: components["schemas"]["QuestRule-Input"][] | null;
            rating?: components["schemas"]["Rating"] | null;
            recommended_players?: components["schemas"]["RecommendedPlayers"] | null;
            /** Reroll Allowed */
            reroll_allowed?: boolean | null;
            /** Routes */
            routes?: components["schemas"]["RouteRule-Input"][] | null;
            /** Rulebook Id */
            rulebook_id?: string | null;
            /** Start Place */
            start_place?: string | null;
            /** Starting Items */
            starting_items?: components["schemas"]["ItemStack-Input"][] | null;
            /** Title */
            title?: string | null;
            /** Traps */
            traps?: components["schemas"]["PlacedTrap-Input"][] | null;
            /** Wanders */
            wanders?: components["schemas"]["WanderTable-Input"][] | null;
            /** World Id */
            world_id?: string | null;
        };
        /**
         * SceneCastOut
         * @description 가장 최근 라운드의 장면에 나온 인물들과 몬스터들. 인물은 판의 인물 순서, 몬스터는 판의 몬스터 순서와 번호 순서다.
         *
         *     인물은 자리가 있으면 살아 있는 캐릭터가 서 있는 장소들의 인물, 없으면 장면에 이름이나 호칭이 나온 인물이다(#282).
         *     로어북의 내용은 싣지 않는다. 몬스터는 살아 있는 캐릭터가 서 있는 장소들의 마리다. 도감의 글은 싣지 않는다.
         */
        SceneCastOut: {
            /**
             * Monsters
             * @default []
             */
            monsters: components["schemas"]["SceneMonsterOut"][];
            /** People */
            people: components["schemas"]["PersonOut"][];
            /** Round */
            round: number;
        };
        /**
         * SceneMonsterOut
         * @description 이번 장면의 몬스터 한 마리. 자기가 선 장소의 죽지 않은 마리를 행동으로 칠 수 있다.
         *
         *     능력치와 HP 의 숫자는 싣지 않는다. 몸 상태를 말로만 싣는다.
         */
        SceneMonsterOut: {
            /** Condition */
            condition: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Injuries
             * @default []
             */
            injuries: string[];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["CarriedOut"][];
            /** Name */
            name: string;
            /**
             * Place Id
             * Format: uuid
             */
            place_id: string;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceOut"][];
            status: components["schemas"]["NpcStatus"];
        };
        /**
         * ScoreRoll
         * @description 능력치의 점수 하나를 주사위로 정하는 법. 예: 4d6 을 굴려 높은 셋을 더한다.
         *
         *     count 개의 sides 면 주사위를 굴려, 높은 것부터 keep 개를 더한 값이 점수 하나다.
         *     이것을 능력치의 수만큼 되풀이한다. 능력치가 여섯이면 점수 여섯이 나온다.
         */
        ScoreRoll: {
            /** Count */
            count: number;
            /** Keep */
            keep: number;
            /** Sides */
            sides: number;
        };
        /**
         * SearchAction
         * @description 지금 서 있는 장소에서 숨긴 길과 숨긴 물건을 찾는 행동(app/rounds/map_actions.py). 받는 값이 없다.
         *
         *     무엇으로 굴리는지(능력과 난이도)는 길과 물건마다 판에 적혀 있다. 플레이어는 숨긴 것이 있는지조차 모른다.
         *     찾은 물건은 찾은 사람이 바로 갖는다.
         */
        SearchAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "search";
        };
        /**
         * SearchOut
         * @description 찾은 결과. 엔진이 정했다(app/rounds/map_actions.py, app/rounds/place_item_actions.py).
         *
         *     찾은 길과 물건만 있다. 굴린 판정과 못 찾은 것은 없다. 숨긴 것이 없는 곳과, 있는데 못 찾은 곳의 결과가 같다.
         */
        SearchOut: {
            /** Found */
            found: components["schemas"]["FoundRouteOut"][];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["FoundItemOut"][];
            place: components["schemas"]["PlaceRefOut"] | null;
            /**
             * Traps
             * @default []
             */
            traps: components["schemas"]["FoundTrapOut"][];
        };
        /**
         * SearchOutcome
         * @description 찾는 행동의 결과.
         */
        SearchOutcome: {
            search: components["schemas"]["SearchOut"];
        };
        /**
         * SellAction
         * @description 가진 물건(item) count 개를 이번 장면의 상인(npc)에게 파는 행동(app/rounds/trades.py, #278).
         *
         *     판정이 없다. 받는 돈은 물건 하나의 값에 화폐의 백분율을 곱해 내림한 것 × 개수다.
         *     판 물건은 상인의 재고가 되지 않는다.
         *     다 팔거나 하나도 팔지 않는다.
         */
        SellAction: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "sell";
            /**
             * Npc
             * Format: uuid
             */
            npc: string;
        };
        /**
         * SetTrapAction
         * @description 가진 덫 물건(item) 하나를 지금 서 있는 장소에 숨겨 놓는 행동(#806, app/rounds/trap_actions.py). 판정이 없다.
         *
         *     덫은 숨긴 채 남는다. 그 장소에 들어오는 쪽(놓은 사람과 일행도)이 피하는 판정을 굴리고, 실패하면 덫의 효과가 든다.
         *     피하든 못 피하든 덫은 터진다. 덫인 물건은 판의 아이템 규칙에 덫(trap)을 적은 것이다.
         */
        SetTrapAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "set_trap";
        };
        /**
         * Sheet
         * @description 캐릭터 시트 하나.
         */
        Sheet: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            };
            /** Max Hp */
            max_hp: number;
        };
        /**
         * SheetOut
         * @description 앉은 사람의 캐릭터 시트. 앉은 사람은 서로의 시트를 본다.
         */
        SheetOut: {
            /** Abilities */
            abilities: {
                [key: string]: number;
            };
            /** Dead */
            dead: boolean;
            /** Death Failures */
            death_failures: number;
            /** Death Successes */
            death_successes: number;
            /** Hp */
            hp: number;
            /**
             * Injuries
             * @default []
             */
            injuries: components["schemas"]["InjuryOut"][];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemOut"][];
            /** Max Hp */
            max_hp: number;
            /**
             * Money
             * @default 0
             */
            money: number;
            /** Number */
            number: number;
            /** Place Id */
            place_id?: string | null;
            /**
             * Resistances
             * @default []
             */
            resistances: components["schemas"]["Resistance"][];
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceOut"][];
            /**
             * Skills
             * @default []
             */
            skills: string[];
            /**
             * Worn
             * @default []
             */
            worn: components["schemas"]["WornOut"][];
        };
        /**
         * ShortRest
         * @description 짧은 휴식. minutes 분을 쉬면 heal 등급(Magnitude.key)만큼 회복한다.
         */
        ShortRest: {
            /** Heal */
            heal: string;
            /** Minutes */
            minutes: number;
        };
        /**
         * Skill
         * @description 기술이나 주문 하나(#805). 예: 치유의 손길(마나 2, 동료, 가볍게 회복), 기합(스태미나 1, 자신, 마나 +1),
         *     마력 화살(마나 1, 상대, 맞히면 가벼운 피해).
         *
         *     key 는 시트(아는 기술)와 행동이 가리키는 이름표, name 은 보이는 이름이다.
         *     cost 는 쓸 때 내는 비용이다. 비우면 공짜다. 빗나가도 낸다. 모자라면 쓰지 못한다.
         *     target 은 누구에게 쓰나다. effects 는 대상에게 적힌 차례대로 드는 일들이다. 소모품의 효과와 같다
         *     (app/engine/item_effects.py, 화염구와 화염병이 같은 damage). 효과가 없으면 쓰고 아무 일도 없다(서술이 맡는다).
         *     check 는 맞히는 판정이다(#805 ②). 자기 자신에게는 굴리지 않는다. 그래서 자신에게만 쓰는 기술에는 적지 않는다.
         *       - 동료에게 쓰는 기술: 적으면 자기 아닌 동료에게 쓸 때 굴린다(동료에게 물건을 던지는 것과 같다).
         *         비우면 굴리지 않는다.
         *       - 상대에게 쓰는 기술: 늘 굴린다. 비우면 룰북의 맞히는 판정(rules.item_check)이다.
         *     맞히면 효과가 든다. 피해가 있으면 그 등급의 타격으로 판정해 방어, 세이브, 부상 표, 드롭이 치기와 같다.
         */
        Skill: {
            check?: components["schemas"]["SkillCheck"] | null;
            cost?: components["schemas"]["SkillCost"] | null;
            /**
             * Effects
             * @default []
             */
            effects: (components["schemas"]["HealEffect"] | components["schemas"]["CureEffect"] | components["schemas"]["DamageEffect"] | components["schemas"]["InjureEffect"] | components["schemas"]["AdjustEffect"])[];
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** @default self */
            target: components["schemas"]["SkillTarget"];
        };
        /**
         * SkillAction
         * @description 기술이나 주문을 쓰는 행동(#805, app/rounds/skill_actions.py).
         *
         *     skill 은 룰북의 기술(rules.skills)의 이름표다. 시트가 그 기술을 알아야 한다(시나리오의 시트에 적는다).
         *     받는 쪽은 하나다. 자신과 동료에게 쓰는 기술은 앉은 사람(target)이고, 비우면 자기 자신이다(받을 때 채운다).
         *     자신에게만 쓰는 기술(target self)에는 남을 적지 않는다. 상대에게 쓰는 기술(target foe, #805 ②)은 이번 장면의
         *     인물(npc)이나 같은 장소의 몬스터(monster)다. 비용은 쓸 때 낸다. 맞히는 판정이 있는 기술은 자기 아닌 쪽에게 굴린다.
         *     lethal 은 피해가 있는 기술을 인물이나 몬스터에게 쓸 때, 치기와 같다. 죽이려는 것인가, 아니면 제압이다.
         */
        SkillAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "skill";
            /**
             * Lethal
             * @default false
             */
            lethal: boolean;
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
            /** Skill */
            skill: string;
            /** Target */
            target?: string | null;
        };
        /**
         * SkillCheck
         * @description 기술의 맞히는 판정(#805 ②). 어느 능력으로, 어느 난이도에 도전하는가. 난이도를 비우면 룰북의 기본 난이도다.
         *
         *     물건의 던지는 판정(items[].throw)과 같다. 능력치와 난이도가 규칙에 있는지는 규칙(Ruleset)이 본다.
         */
        SkillCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * SkillCost
         * @description 기술 한 번의 비용(#805). 쓰는 사람의 수치(resources 의 key) 하나를 그만큼 낸다.
         */
        SkillCost: {
            /** Amount */
            amount: number;
            /** Resource */
            resource: string;
        };
        /**
         * SkillTarget
         * @description 기술을 누구에게 쓰나(#805).
         * @enum {string}
         */
        SkillTarget: "self" | "ally" | "foe";
        /**
         * SkillUseOut
         * @description 기술을 쓴 결과(#805). 엔진이 정했다(app/rounds/skill_actions.py).
         *
         *     상대(인물, 몬스터)에게 쓰거나 판정이 있는 기술을 자기 아닌 동료에게 쓰면 맞히는 판정을 한다(#805 ②). 그때는 판정의
         *     결과(CheckOutcome)의 skill_use 로 오고, 맞혔을 때만 효과(cured, injured, resources)가 있다.
         *     비용은 빗나가도 낸다. 쓰지 못했으면 내지 않는다.
         */
        SkillUseOut: {
            /** Ability */
            ability?: string | null;
            /**
             * Cost
             * @default []
             */
            cost: components["schemas"]["ResourceShiftOut"][];
            /**
             * Cured
             * @default []
             */
            cured: components["schemas"]["CuredOut"][];
            /** Difficulty */
            difficulty?: string | null;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /** Name */
            name: string;
            /** Reason */
            reason: string | null;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /** Skill */
            skill: string;
            /** Target */
            target: components["schemas"]["ItemPersonOut"] | components["schemas"]["ThrownAtOut"] | null;
            /** Used */
            used: boolean;
        };
        /**
         * SkillUseOutcome
         * @description 기술을 쓰는 행동의 결과(#805). 회복하거나 다쳤으면 HP 의 변화(effect)가 함께 있다. 굴림이 없다.
         *
         *     굴리는 기술을 쓰지 못했으면 여기로 온다. 겨눈 몬스터가 없어 못 썼으면 그 까닭(target_gone)도 있다(#805 ②).
         */
        SkillUseOutcome: {
            effect?: components["schemas"]["EffectOut"] | null;
            skill_use: components["schemas"]["SkillUseOut"];
            target_gone?: components["schemas"]["TargetGoneOut"] | null;
        };
        /**
         * Snapshot
         * @description 판 하나의 내용 전부. 플레이에 필요한 것이 이 안에 다 있다.
         *
         *     각 자산의 id 는 굳힐 때의 초안을 가리킨다. 어디서 왔는지 알려 줄 뿐이고, 판을 읽을 때 초안을 다시 보지 않는다.
         *     gm_guide 와 gm_notes 가 들어 있다. 만든 사람이 아닌 사람에게 이 문서를 그대로 내주면 안 된다.
         */
        Snapshot: {
            /** Character Modes */
            character_modes: components["schemas"]["CharacterMode"][];
            /**
             * @default {
             *       "round_minutes": 10,
             *       "start_day": 1,
             *       "start_hour": 8
             *     }
             */
            clock: components["schemas"]["ClockSnapshot"];
            /**
             * Covers
             * @default []
             */
            covers: components["schemas"]["CoverSnapshot"][];
            currency?: components["schemas"]["CurrencySnapshot"] | null;
            default_npc_sheet: components["schemas"]["Sheet"] | null;
            default_sheet: components["schemas"]["CharacterSheet"] | null;
            /** Description */
            description: string;
            /**
             * Encounters
             * @default []
             */
            encounters: components["schemas"]["EncounterSnapshot"][];
            /**
             * Format
             * @default 67
             */
            format: number;
            /**
             * Happenings
             * @default []
             */
            happenings: components["schemas"]["HappeningSnapshot"][];
            /**
             * Items
             * @default []
             */
            items: components["schemas"]["ItemRuleSnapshot"][];
            /**
             * Landmarks
             * @default []
             */
            landmarks: string[];
            /** Lorebooks */
            lorebooks: components["schemas"]["LorebookSnapshot"][];
            /**
             * Monsters
             * @default []
             */
            monsters: components["schemas"]["MonsterSnapshot"][];
            narration_style: components["schemas"]["NarrationStyle"];
            /**
             * Npc Places
             * @default []
             */
            npc_places: components["schemas"]["NpcPlaceSnapshot"][];
            /** Npc Sheets */
            npc_sheets: components["schemas"]["NpcSheetSnapshot"][];
            /** Openings */
            openings: string[];
            /**
             * Place Items
             * @default []
             */
            place_items: components["schemas"]["PlaceItemSnapshot"][];
            player_made_hp: components["schemas"]["PlayerMadeHpSnapshot"] | null;
            /** Pregens */
            pregens: components["schemas"]["PregenSnapshot"][];
            /**
             * Quests
             * @default []
             */
            quests: components["schemas"]["QuestRuleSnapshot"][];
            rating: components["schemas"]["Rating"];
            recommended_players: components["schemas"]["PlayersSnapshot"];
            /** Reroll Allowed */
            reroll_allowed: boolean;
            /**
             * Routes
             * @default []
             */
            routes: components["schemas"]["RouteSnapshot"][];
            rulebook: components["schemas"]["RulebookSnapshot"];
            /** Start Place */
            start_place?: string | null;
            /**
             * Starting Items
             * @default []
             */
            starting_items: components["schemas"]["ItemStackSnapshot"][];
            /** Title */
            title: string;
            /**
             * Traps
             * @default []
             */
            traps: components["schemas"]["PlacedTrapSnapshot"][];
            /**
             * Wanders
             * @default []
             */
            wanders: components["schemas"]["WanderTableSnapshot"][];
            world: components["schemas"]["WorldSnapshot"] | null;
        };
        /**
         * Steal
         * @description 훔치기(app/rounds/steals.py). 어느 능력으로 판정하고, 무엇이 목표값을 올리고 내리는가.
         *
         *     목표값은 difficulty 의 목표값에서 시작한다. 더하는 것과 빼는 것은 걸리는 만큼 모두 더한다. 1 보다 낮아지지 않는다.
         *       - 대상의 눈치(awareness): 대상의 그 능력치의 보정만큼 더한다(둔하면 음수라 내려간다). None 이면 보지 않는다.
         *       - 장비(equipped): 걸치거나 쥔 것을 훔치면 더한다.
         *       - 등급(rarity_step): 물건의 등급이 노말에서 한 단계 오를 때마다 더한다.
         *       - 둔한 타입(dull_kinds): 대상의 타입이 그것이면 뺀다. 둔함 표시(dull): 판에 둔하다고 적은 대상이면 뺀다.
         *       - 싸움 전(unwary): 대상이 아직 아무와도 싸우지 않았으면(쓰러져 있어도) 뺀다.
         *       - 정신이 팔림(distracted): 이번 라운드에 도둑의 차례 전에 대상이 다른 사람과 싸웠으면 뺀다.
         */
        Steal: {
            /** Ability */
            ability: string;
            /** Awareness */
            awareness: string | null;
            /** Difficulty */
            difficulty: string;
            /** Distracted */
            distracted: number;
            /** Dull */
            dull: number;
            /** Dull Kinds */
            dull_kinds: components["schemas"]["DullKind"][];
            /** Equipped */
            equipped: number;
            /** Rarity Step */
            rarity_step: number;
            /** Unwary */
            unwary: number;
        };
        /**
         * StealAction
         * @description 같은 장소의 몬스터 한 마리(monster)나 이번 장면의 인물(npc)이 지닌 물건 하나(item)를 훔치는 행동
         *     (app/rounds/steals.py). monster 와 npc 중 하나만 적는다.
         *
         *     능력과 난이도는 받지 않는다. 규칙(Ruleset.steal)이 정하고, 물건과 대상에 따라 목표값이 오르내린다.
         *     성공하면 그 줄을 통째로 갖는다. 들키면 몬스터는 이번 라운드의 차례에 도둑을 노린다.
         *     NPC 는 적대가 되고, 그 인물의 시트가 정했으면(on_caught: fight) 싸움도 붙는다(#457).
         */
        StealAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "steal";
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
        };
        /**
         * StealOut
         * @description 훔친 결과. 엔진이 정했다(app/rounds/steals.py).
         *
         *     대상이 몬스터면 monster_id 와 monster_name 이, NPC 면 npc_id(인물 항목의 id)와 npc_name(장면의 호칭)이 있다.
         *     stolen 이 참이면 훔쳤다(count 는 훔친 개수, left 는 대상에게 남은 개수, total 은 도둑이 가진 개수).
         *     거짓이고 check 가 있으면 들켰다. 몬스터는 이번 라운드의 차례에 도둑을 친다(fight 가 늘 참이다).
         *     NPC 는 적대가 되고(attitude_change, 이미 적대였으면 None), 시트가 정했으면 싸움도 붙는다(fight).
         *     check 가 없으면 굴리지 않았다(reason 이 gone: 앞사람이 먼저 훔쳤다). full 은 상한에 닿아 그만큼만 훔친 것이다.
         *     factors 는 목표값을 오르내리게 한 것들이다(equipped, rarity, dull_kind, dull, unwary, distracted).
         *     대상의 눈치(능력치의 보정)는 늘 보지만 대상의 숫자라 따로 적지 않는다. target 에 섞여 있다.
         */
        StealOut: {
            attitude_change?: components["schemas"]["AttitudeChangeOut"] | null;
            /** Character Name */
            character_name: string;
            check: components["schemas"]["RolledOut"] | null;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Factors */
            factors: string[];
            /**
             * Fight
             * @default false
             */
            fight: boolean;
            hindrance: components["schemas"]["HindranceOut"] | null;
            /** Left */
            left: number;
            /** Monster Id */
            monster_id?: string | null;
            /** Monster Name */
            monster_name?: string | null;
            /** Name */
            name: string;
            /** Npc Id */
            npc_id?: string | null;
            /** Npc Name */
            npc_name?: string | null;
            /** Reason */
            reason: string | null;
            /** Stolen */
            stolen: boolean;
            /** Total */
            total: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * StealOutcome
         * @description 훔치는 행동의 결과.
         */
        StealOutcome: {
            steal: components["schemas"]["StealOut"];
        };
        /**
         * StepPriceOut
         * @description 모델의 단계 하나와 1인 1라운드의 값(#387). 결제 서버 없이 도는 서버면 credits 와 tier 가 null 이다.
         *
         *     입력 단계마다 입력 +8,000 토큰(12,000, 20,000, 28,000), 출력 단계마다 출력 +1,000 토큰(1,200, 2,200, 3,200)이다.
         *     입력이 크면 지난 기록, 로어북, 기억이 더 들어가고, 출력이 크면 장면이 길어진다.
         */
        StepPriceOut: {
            /** Credits */
            credits: string | null;
            /** Input Step */
            input_step: number;
            /** Input Tokens */
            input_tokens: number;
            next: components["schemas"]["NextPriceOut"] | null;
            /** Output Step */
            output_step: number;
            /** Output Tokens */
            output_tokens: number;
            /** Promo */
            promo: boolean;
            tier: components["schemas"]["Tier"] | null;
        };
        /**
         * Surprise
         * @description 조우에서 누가 기습하는가. 제작자가 조우마다 정한다.
         *
         *     기습한 쪽은 만난 첫 라운드(살아 있는 캐릭터가 그 장소에서 처음 차례를 받는 라운드)에 모두 먼저 움직인다.
         *     그다음부터는 차례를 정하는 능력치(Ruleset.initiative_ability)의 순서다. 순서를 정하는 것은 라운드 닫기다.
         * @enum {string}
         */
        Surprise: "none" | "monsters" | "party";
        /**
         * TableCreate
         * @description 테이블을 만들 때 받는 값. 어느 시나리오의 어느 판으로, 어느 스타팅으로, 몇 명이서 할지 고른다.
         *
         *     version 을 비우면 그 시나리오의 공개 중인 판을 쓴다. 번호를 적는 것은 자기 시나리오일 때만 된다.
         *     is_public 을 켜면 로비에 보인다. 만든 뒤에는 바꿀 수 없다. 비밀번호는 로비에 보이는 테이블에만 건다.
         *     character_modes 로 캐릭터 방식을 좁힌다. 판이 허용한 것 중에서만 고른다. 비우면 판이 허용한 그대로다.
         */
        TableCreate: {
            /** Capacity */
            capacity: number;
            /** Character Modes */
            character_modes?: components["schemas"]["CharacterMode"][] | null;
            /**
             * Credit Wait Seconds
             * @default 300
             */
            credit_wait_seconds: number;
            /**
             * Input Step
             * @default 0
             */
            input_step: number;
            /**
             * Is Public
             * @default false
             */
            is_public: boolean;
            /** Narration Model */
            narration_model?: string | null;
            narration_style?: components["schemas"]["NarrationStyle"] | null;
            /**
             * Opening Index
             * @default 0
             */
            opening_index: number;
            /**
             * Output Step
             * @default 0
             */
            output_step: number;
            /** Password */
            password?: string | null;
            /**
             * References Enabled
             * @default false
             */
            references_enabled: boolean;
            /**
             * Remove Short Payers
             * @default true
             */
            remove_short_payers: boolean;
            /**
             * Round Time Limit
             * @default 300
             */
            round_time_limit: number | null;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Version */
            version?: number | null;
            /**
             * Whisper Notice
             * @default false
             */
            whisper_notice: boolean;
        };
        /**
         * TableDetail
         * @description 참가자가 테이블을 볼 때의 값. 여기 적힌 칸만 나간다.
         *
         *     GM 전용 글(룰북의 진행 지침, 세계관의 GM 전용 설정, 로어북)은 싣지 않는다. 방장에게도 싣지 않는다.
         */
        TableDetail: {
            /** Capacity */
            capacity: number;
            /** Character Modes */
            character_modes: components["schemas"]["CharacterMode"][];
            clock: components["schemas"]["ClockOut"];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Credit Wait Seconds */
            credit_wait_seconds: number;
            currency?: components["schemas"]["CurrencyOut"] | null;
            default_sheet: components["schemas"]["CharacterSheet"] | null;
            /** Ended At */
            ended_at: string | null;
            friendly_fire: components["schemas"]["FriendlyFire"];
            /** Has Password */
            has_password: boolean;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Step */
            input_step: number;
            /** Invite Code */
            invite_code: string | null;
            /** Is Public */
            is_public: boolean;
            /** Items */
            items: components["schemas"]["CatalogItemOut"][];
            map: components["schemas"]["MapOut"] | null;
            /** Member Count */
            member_count: number;
            /** Members */
            members: components["schemas"]["MemberOut"][];
            /** Narration Model */
            narration_model: string | null;
            narration_style: components["schemas"]["NarrationStyle"];
            /** Opening */
            opening: string;
            /** Output Step */
            output_step: number;
            player_made_hp: components["schemas"]["PlayerMadeHp"] | null;
            /** Pregens */
            pregens: components["schemas"]["PregenChoice"][];
            /** Quests */
            quests: components["schemas"]["QuestOut"][];
            rating: components["schemas"]["Rating"];
            recommended_narration_style: components["schemas"]["NarrationStyle"];
            recommended_players: components["schemas"]["RecommendedPlayers"];
            /** References Enabled */
            references_enabled: boolean;
            /** Remove Short Payers */
            remove_short_payers: boolean;
            /** Reroll Allowed */
            reroll_allowed: boolean;
            /** Round Time Limit */
            round_time_limit: number | null;
            rules: components["schemas"]["Ruleset"];
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            /** Started At */
            started_at: string | null;
            status: components["schemas"]["TableStatus"];
            /** Title */
            title: string;
            /** Whisper Notice */
            whisper_notice: boolean;
        };
        /**
         * TablePage
         * @description 테이블 목록의 한 쪽.
         */
        TablePage: {
            /** Items */
            items: components["schemas"]["TableSummary"][];
            /** Total */
            total: number;
        };
        /**
         * TableRow
         * @description 부상 표의 한 줄. 눈이 low 이상 high 이하면 이 줄이다. injury 가 None 이면 부상이 없다.
         */
        TableRow: {
            /** High */
            high: number;
            /** Injury */
            injury: string | null;
            /** Low */
            low: number;
        };
        /**
         * TableStatus
         * @description 테이블의 상태. 한 방향으로만 나아간다.
         * @enum {string}
         */
        TableStatus: "recruiting" | "playing" | "ended";
        /**
         * TableSummary
         * @description 테이블의 목록에 싣는 값.
         */
        TableSummary: {
            /** Capacity */
            capacity: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Credit Wait Seconds */
            credit_wait_seconds: number;
            friendly_fire: components["schemas"]["FriendlyFire"];
            /** Has Password */
            has_password: boolean;
            /**
             * Host Id
             * Format: uuid
             */
            host_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Input Step */
            input_step: number;
            /** Is Public */
            is_public: boolean;
            /** Member Count */
            member_count: number;
            /** Narration Model */
            narration_model: string | null;
            narration_style: components["schemas"]["NarrationStyle"];
            /** Output Step */
            output_step: number;
            rating: components["schemas"]["Rating"];
            /** References Enabled */
            references_enabled: boolean;
            /** Remove Short Payers */
            remove_short_payers: boolean;
            /** Round Time Limit */
            round_time_limit: number | null;
            /**
             * Scenario Id
             * Format: uuid
             */
            scenario_id: string;
            status: components["schemas"]["TableStatus"];
            /** Title */
            title: string;
            /** Whisper Notice */
            whisper_notice: boolean;
        };
        /**
         * TakeAction
         * @description 지금 서 있는 장소에 보이게 놓인 물건(item) count 개를 줍는 행동(app/rounds/place_item_actions.py).
         *
         *     item 은 판의 로어북 물건 항목의 id 다. 판정이 없다. 남은 것보다 많이 부르면 남은 만큼, 한 가지의 상한까지 줍는다.
         */
        TakeAction: {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "take";
        };
        /**
         * TakeOut
         * @description 주운 결과. 엔진이 정했다(app/rounds/place_item_actions.py). 판정이 없다.
         *
         *     count 는 부른 개수, taken 은 주운 개수다. 다 줍지 못했으면 reason 이 있다
         *     (gone: 남은 것이 없었다, not_enough: 남은 만큼 주웠다, full: 한 가지의 상한에 닿았다).
         */
        TakeOut: {
            /** Character Name */
            character_name: string;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            place: components["schemas"]["PlaceRefOut"] | null;
            /** Reason */
            reason: string | null;
            /** Taken */
            taken: number;
            /** Total */
            total: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * TakeOutcome
         * @description 줍는 행동의 결과.
         */
        TakeOutcome: {
            take: components["schemas"]["TakeOut"];
        };
        /**
         * TargetGoneOut
         * @description 판정할 때 겨눈 몬스터(나 훔치려던 NPC, 해치려던 동료)를 겨눌 수 없었던 것. 엔진은 굴리지 않았다.
         */
        TargetGoneOut: {
            /** Monster Id */
            monster_id?: string | null;
            /** Name */
            name: string | null;
            /** Npc Id */
            npc_id?: string | null;
            /** Reason */
            reason: string;
            /** User Id */
            user_id?: string | null;
        };
        /**
         * TargetGoneOutcome
         * @description 몬스터를 겨눈 판정을 굴리지 못한 결과. 판정의 결과(CheckOutcome)와 달리 굴림이 없다.
         */
        TargetGoneOutcome: {
            target_gone: components["schemas"]["TargetGoneOut"];
        };
        /**
         * Template
         * @description 고를 수 있는 템플릿. 이름마다 이 폴더에 {이름}.json 이 있다.
         * @enum {string}
         */
        Template: "srd5" | "horror" | "light";
        /**
         * TemplateList
         * @description 고를 수 있는 템플릿들. app/engine/templates/ 의 Template 에 적은 차례다.
         *
         *     default 는 룰북을 만들 때 template 을 보내지 않으면 쓰는 것이다.
         */
        TemplateList: {
            default: components["schemas"]["Template"];
            /** Items */
            items: components["schemas"]["TemplateSummary"][];
        };
        /**
         * TemplateSummary
         * @description 고를 수 있는 템플릿 하나(#615). 룰북을 만들 때 template 에 key 를 보내면 rules 가 룰북에 복사된다.
         *
         *     attribution 은 본뜬 공개 문서의 출처 표시다. 화면에 템플릿을 보여 줄 때 함께 싣는다.
         */
        TemplateSummary: {
            /** Attribution */
            attribution: string[];
            key: components["schemas"]["Template"];
            /** Name */
            name: string;
            /** Notes */
            notes: string[];
            rules: components["schemas"]["Ruleset"];
            /** Summary */
            summary: string;
        };
        /**
         * ThrowAction
         * @description 물건을 던지는 행동(#277). 가진 물건 하나를 몬스터 한 마리(monster)나 이번 장면의 인물(npc)이나
         *     앉은 사람(target, #803)에게 던진다. 앉은 사람에게 해로운 물건을 던지는 것은 테이블과 맞는 쪽의 설정이 정한다.
         *
         *     item 은 판의 로어북 물건 항목의 id 다. 어떤 물건이든 된다(#801). 능력과 난이도는 받지 않는다. 물건의 던지는
         *     판정(아이템 규칙의 throw)이나 룰북의 맞히는 판정(rules.item_check)으로 판정한다(app/rounds/throws.py).
         *     맞히면 그 물건의 효과가 든다. 피해가 있으면 방어와 세이브는 치기와 같다. 맞든 빗나가든 물건은 하나 없어진다.
         *     lethal 은 피해가 있는 물건에만, 치기와 같다. 죽이려는 것인가, 아니면 제압이다. 노려 치기와 무기는 없다.
         */
        ThrowAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "throw";
            /**
             * Lethal
             * @default false
             */
            lethal: boolean;
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
            /** Target */
            target?: string | null;
        };
        /**
         * ThrownAtOut
         * @description 물건을 던진 쪽(#277). 몬스터면 monster_id, 인물이면 entry_id, 앉은 사람(#803)이면 user_id 가 있다.
         *     이름은 장면에서 부르는 것이다. 앉은 사람이면 캐릭터의 이름이다.
         */
        ThrownAtOut: {
            /** Entry Id */
            entry_id?: string | null;
            /** Monster Id */
            monster_id?: string | null;
            /** Name */
            name: string | null;
            /** User Id */
            user_id?: string | null;
        };
        /**
         * Tier
         * @description 결제 서버 가격표의 등급. 결제에 쓰는 등급은 이것이 기준이다(model-pricing-plan 9-1).
         *
         *     결제 서버가 모르는 등급을 보내면 목록 전체를 읽지 못한다(503).
         *     그래서 결제 서버는 게임 서버가 등급을 안 뒤에 그 줄을 넣는다.
         * @enum {string}
         */
        Tier: "basic" | "standard" | "premium";
        /**
         * TimeOfDay
         * @description 하루의 어느 때. 서술이 밝기와 분위기를 맞추는 데 쓴다.
         * @enum {string}
         */
        TimeOfDay: "dawn" | "morning" | "day" | "evening" | "night";
        /**
         * TradeOut
         * @description 상인과 사고판 결과(#278). 엔진이 정했다(app/rounds/trades.py). 판정이 없다.
         *
         *     side 는 buy(샀다)나 sell(팔았다)이다. npc_id 는 상인의 인물 항목의 id, npc_name 은 장면의 호칭이다.
         *     price 는 오간(오가려던) 돈이다. 살 때는 낸 돈, 팔 때는 받은 돈이다. 다 하거나 하나도 하지 않는다.
         *     traded 가 거짓이면 reason 이 있다: unavailable(상인이 쓰러졌거나 죽었거나 적대했다), out_of_stock(재고가 모자랐다),
         *     not_enough_money(돈이 모자랐다), not_held(팔 물건이 모자랐다), full(산 물건을 더 가질 수 없었다),
         *     too_much_money(받을 돈을 더 가질 수 없었다).
         *     total 은 그 뒤에 그 물건을 가진 개수, money 는 그 뒤에 가진 돈이다.
         */
        TradeOut: {
            /** Character Name */
            character_name: string;
            /** Count */
            count: number;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Money */
            money: number;
            /** Name */
            name: string;
            /**
             * Npc Id
             * Format: uuid
             */
            npc_id: string;
            /** Npc Name */
            npc_name: string;
            /** Price */
            price: number;
            /** Reason */
            reason: string | null;
            /** Side */
            side: string;
            /** Total */
            total: number;
            /** Traded */
            traded: boolean;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * TradeOutcome
         * @description 사거나 파는 행동의 결과.
         */
        TradeOutcome: {
            trade: components["schemas"]["TradeOut"];
        };
        /**
         * TranscriptFormat
         * @description 기록의 형식.
         * @enum {string}
         */
        TranscriptFormat: "md" | "html" | "txt";
        /**
         * TrapCaughtOut
         * @description 덫에 함께 걸린 업힌 사람(#806 ②)과 그 사람에게 든 효과. 업은 사람이 피했으면 효과가 비어 있다.
         */
        TrapCaughtOut: {
            /** Character Name */
            character_name: string;
            effect?: components["schemas"]["EffectOut"] | null;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * TrapCheck
         * @description 덫의 판정 하나(#806). 피하기(avoid)와 해제(disarm)가 이 모양이다. 능력치와 난이도(비우면 룰북의 기본)다.
         *     룰북의 규칙에 있는지는 게시할 때 본다(item_trap_invalid).
         */
        TrapCheck: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * TrapCheckOut
         * @description 덫의 판정 하나(#806). 능력치와 난이도(비면 rules 의 기본)다.
         */
        TrapCheckOut: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string | null;
        };
        /**
         * TrapCheckSnapshot
         * @description 덫의 판정 하나(#806). 능력치와 난이도(없으면 룰북의 기본)다.
         */
        TrapCheckSnapshot: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty?: string | null;
        };
        /**
         * TrapSetOut
         * @description 덫을 놓은 결과(#806). 엔진이 정했다(app/rounds/trap_actions.py). 판정이 없다.
         *
         *     set 이 참이면 그 장소에 숨겨 놓였다. 차례가 왔을 때 가지고 있지 않았으면 놓지 않았다(reason 이 not_held).
         */
        TrapSetOut: {
            /** Character Name */
            character_name: string;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            place: components["schemas"]["PlaceRefOut"] | null;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            /** Set */
            set: boolean;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * TrapSetOutcome
         * @description 덫을 놓는 행동의 결과.
         */
        TrapSetOutcome: {
            trap_set: components["schemas"]["TrapSetOut"];
        };
        /**
         * TrapSprungOut
         * @description 들어간 장소에서 터진 덫 하나(#806). 엔진이 정했다(app/rounds/trap_actions.py). 굴림은 공개다.
         *
         *     피하는 판정(avoid)에 성공하면 피했다(avoided). 못 피했으면 효과가 들었다(effect, injured, resources).
         *     피했든 못 피했든 덫은 터져 끝났다.
         */
        TrapSprungOut: {
            avoid: components["schemas"]["CrossOut"];
            /** Avoided */
            avoided: boolean;
            carried?: components["schemas"]["TrapCaughtOut"] | null;
            effect?: components["schemas"]["EffectOut"] | null;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /** Name */
            name: string;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            /** Set By */
            set_by: string | null;
            /**
             * Trap Id
             * Format: uuid
             */
            trap_id: string;
        };
        /**
         * TreatAction
         * @description 치료하는 행동. 대상이 입은 오래 가는 부상 하나를 치료한다.
         *
         *     능력과 난이도는 받지 않는다. 규칙의 치료 능력과 그 부상의 치료 난이도로 판정한다.
         *     대상은 앉은 사람(target)이나 이번 장면의 NPC(npc) 중 하나다.
         *     둘 다 비우면 자기 자신이다(app/rounds/acceptance.py 가 채운다).
         *     item 은 치료에 붙여 쓰는 물건이다(#277, #802, 의료 키트). 치료를 거드는 물건(아이템 규칙의 aids)이어야 한다.
         *     그 보정만큼 치료 판정의 보정이 오르고, 굴린 뒤 그 물건의 방식대로 없어진다. 비우면 물건 없이 치료한다.
         */
        TreatAction: {
            /** Injury */
            injury: string;
            /** Item */
            item?: string | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "treat";
            /** Npc */
            npc?: string | null;
            /** Target */
            target?: string | null;
        };
        /**
         * Treatment
         * @description 치료의 규칙. 어느 능력으로 판정하고, 실패하면 무엇이 일어나는지.
         *
         *     난이도와 앞당기는 시간은 부상마다 다르다(Injury.treat_difficulty, treat_minutes).
         */
        Treatment: {
            /** Ability */
            ability: string;
            mishaps: components["schemas"]["MishapTable"];
        };
        /**
         * TreatmentOut
         * @description 치료의 결과. 엔진이 정한 것이다. 판정의 능력과 난이도는 규칙이 정한 치료의 것이다.
         */
        TreatmentOut: {
            /** Ability */
            ability: string;
            aftermath: components["schemas"]["InjuryRollOut"] | null;
            aid?: components["schemas"]["AidOut"] | null;
            /** Died */
            died: boolean;
            /** Difficulty */
            difficulty: string;
            /** Healed */
            healed: boolean;
            heals_at?: components["schemas"]["ClockTimeOut"] | null;
            /** Injury */
            injury: string;
            /** Minutes Left */
            minutes_left?: number | null;
            mishap: components["schemas"]["MishapOut"] | null;
            /** Name */
            name: string;
            patient: components["schemas"]["PatientOut"];
            /** Treated */
            treated: boolean;
        };
        /**
         * TurnLostOutcome
         * @description 차례가 오기 전에 캐릭터가 쓰러지거나 죽어 행동하지 못한 결과. 엔진은 굴리지 않았다.
         */
        TurnLostOutcome: {
            /** Turn Lost */
            turn_lost: string;
        };
        /**
         * UnlockAction
         * @description 지금 서 있는 장소에 닿은 길의 문을 여는 행동(#281). 지나가지 않고 열기만 한다. device 는 잠그기와 같다.
         *
         *     자물쇠는 그 열쇠를 지녀야 열고, 빗장은 빗장 쪽에 서 있어야 푼다.
         */
        UnlockAction: {
            device?: components["schemas"]["DoorDevice"] | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "unlock";
            /**
             * Place
             * Format: uuid
             */
            place: string;
        };
        /**
         * UseAction
         * @description 물건을 쓰는 행동. 가진 소모품 하나를 쓴다(app/rounds/item_actions.py).
         *
         *     item 은 판의 로어북 물건 항목의 id 다. 소모품이어야 한다. 엔진은 이 값을 읽지 않는다. 어떤 물건인지는 판이 안다.
         *     효과가 있는 소모품(#800)이면 대상에게 그 효과들이 든다. 대상은 앉은 사람(target, 비우면 자기 자신.
         *     app/rounds/acceptance.py 가 채운다), 이번 장면의 인물(npc), 같은 장소의 몬스터(monster) 중 하나다.
         *     인물과 몬스터에게는 맞히는 판정을 거친다. lethal 은 피해가 있는 물건을 인물이나 몬스터에게 쓸 때 치기와 같다.
         *     효과가 없는 소모품(연막탄 같은 것)은 대상이 없다. 쓰고 없어진다. 무엇이 일어나는지는 서술이 맡는다.
         */
        UseAction: {
            /**
             * Item
             * Format: uuid
             */
            item: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "use";
            /**
             * Lethal
             * @default false
             */
            lethal: boolean;
            /** Monster */
            monster?: string | null;
            /** Npc */
            npc?: string | null;
            /** Target */
            target?: string | null;
        };
        /**
         * VersionCreate
         * @description 게시할 때 받는 값. 변경 내용만 적는다. 비워도 된다.
         *
         *     판의 내용은 받지 않는다. 서버가 초안에서 직접 읽어 굳힌다.
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
         * @description 만든 사람이 자기 판을 볼 때의 값. 굳힌 내용까지 싣는다. GM 전용 글이 들어 있다.
         */
        VersionDetail: {
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
            snapshot: components["schemas"]["Snapshot"];
        };
        /**
         * VersionSummary
         * @description 판의 목록에 싣는 값. 굳힌 내용은 싣지 않는다.
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
         * @description 누구에게 보이는가. 지금은 만든 사람만 본다. 공개 기능을 만들 때 값을 늘린다.
         * @enum {string}
         */
        Visibility: "private";
        /**
         * WaitAction
         * @description 시간을 건너뛰는 행동(app/rounds/waits.py). 얼마나 기다리는지(minutes, 1분~일주일)만 받는다.
         *
         *     앉은 사람이 모두 기다리고 아무도 맞지 않았으면 다음 라운드가 적어도 가장 짧게 부른 시간만큼 뒤에 열린다.
         */
        WaitAction: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "wait";
            /** Minutes */
            minutes: number;
        };
        /**
         * WaitOut
         * @description 기다린 결과. 엔진이 정했다(app/rounds/waits.py). 판정이 없다.
         *
         *     앉은 사람이 모두 기다렸고 아무도 맞지 않았으면 다음 라운드가 적어도 가장 짧게 부른 시간만큼 뒤에 열렸다.
         *     아니면 기다림이 깨져 시간이 건너뛰지 않았다(waited 가 false, reason 이 hurt 또는 not_all).
         */
        WaitOut: {
            /** Minutes */
            minutes: number;
            /** Reason */
            reason: string | null;
            /** Waited */
            waited: boolean;
        };
        /**
         * WaitOutcome
         * @description 기다리는 행동의 결과.
         */
        WaitOutcome: {
            wait: components["schemas"]["WaitOut"];
        };
        /**
         * WakeOut
         * @description 쓰러진 동안 빼앗겼던 NPC 가 깨어날 때의 반응. 엔진이 굴렸다(app/rounds/wakes.py).
         *
         *     roll 은 백면체의 눈, reaction 은 그 눈이 정한 반응(hostile 적대, wary 경계, None 눈치채지 못함)이다.
         *     attitude_change 는 실제로 바뀐 태도다. 이미 그만큼 날 서 있었으면 None 이다.
         */
        WakeOut: {
            attitude_change: components["schemas"]["AttitudeChangeOut"] | null;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            reaction: components["schemas"]["NpcAttitude"] | null;
            /** Roll */
            roll: number;
        };
        /**
         * WanderMonster
         * @description 무작위 조우 표의 한 줄(#283). 붙인 도감의 몬스터 하나(monster_id)가 count 마리 나온다.
         *
         *     weight 는 이 줄이 뽑힐 몫이다. 표의 몫을 모두 더한 것 가운데 이 줄의 몫만큼 뽑힌다.
         *     surprise 는 조우와 같다. 쉬는 중에 나오면 적은 것과 상관없이 몬스터가 기습한다.
         *     몬스터가 시트를 적은 몬스터인지는 게시할 때 본다(조우와 같다).
         */
        "WanderMonster-Input": {
            /**
             * Count
             * @default 1
             */
            count: number;
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
            /**
             * Weight
             * @default 1
             */
            weight: number;
        };
        /**
         * WanderMonster
         * @description 무작위 조우 표의 한 줄(#283). 붙인 도감의 몬스터 하나(monster_id)가 count 마리 나온다.
         *
         *     weight 는 이 줄이 뽑힐 몫이다. 표의 몫을 모두 더한 것 가운데 이 줄의 몫만큼 뽑힌다.
         *     surprise 는 조우와 같다. 쉬는 중에 나오면 적은 것과 상관없이 몬스터가 기습한다.
         *     몬스터가 시트를 적은 몬스터인지는 게시할 때 본다(조우와 같다).
         */
        "WanderMonster-Output": {
            /**
             * Count
             * @default 1
             */
            count: number;
            /** Monster Id */
            monster_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
            /**
             * Weight
             * @default 1
             */
            weight: number;
        };
        /**
         * WanderMonsterSnapshot
         * @description 무작위 조우 표의 한 줄(#283). 판의 몬스터 하나(monster_id)가 count 마리, 뽑힐 몫(weight), 누가 기습하는가.
         */
        WanderMonsterSnapshot: {
            /** Count */
            count: number;
            /**
             * Monster Id
             * Format: uuid
             */
            monster_id: string;
            /** @default none */
            surprise: components["schemas"]["Surprise"];
            /** Weight */
            weight: number;
        };
        /**
         * WanderTable
         * @description 무작위 조우 표 하나(#283). 장소(place_id)에서 하루의 때(times)에 쓰는 표다.
         *
         *     걸리는 시간이 있는 길을 한 칸 와서 그 장소에 닿거나, 그 장소에서 길게 쉬면 엔진이 한 번 굴린다.
         *     chance(0~100)% 로 조우가 나고, 나면 몬스터의 줄 하나를 몫(weight)대로 뽑아 그 장소에 놓는다.
         *     place_id 를 비우면 판의 기본 표다. 표를 하나도 적지 않은 장소에서 쓴다. 기본 표도 없으면 조우가 없다.
         *     times 를 비우면 언제나 쓴다. 한 장소(또는 기본 표)의 표들은 때가 겹치지 않는다. 때가 맞는 표가 없으면 조우가 없다.
         *     chance 가 0 이면 조우가 나지 않는 표다(마을처럼 안전한 곳). 그때는 몬스터를 적지 않는다.
         *     장소가 맵의 장소인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
         */
        "WanderTable-Input": {
            /** Chance */
            chance: number;
            /**
             * Monsters
             * @default []
             */
            monsters: components["schemas"]["WanderMonster-Input"][];
            /** Place Id */
            place_id?: string | null;
            /**
             * Times
             * @default []
             */
            times: components["schemas"]["TimeOfDay"][];
        };
        /**
         * WanderTable
         * @description 무작위 조우 표 하나(#283). 장소(place_id)에서 하루의 때(times)에 쓰는 표다.
         *
         *     걸리는 시간이 있는 길을 한 칸 와서 그 장소에 닿거나, 그 장소에서 길게 쉬면 엔진이 한 번 굴린다.
         *     chance(0~100)% 로 조우가 나고, 나면 몬스터의 줄 하나를 몫(weight)대로 뽑아 그 장소에 놓는다.
         *     place_id 를 비우면 판의 기본 표다. 표를 하나도 적지 않은 장소에서 쓴다. 기본 표도 없으면 조우가 없다.
         *     times 를 비우면 언제나 쓴다. 한 장소(또는 기본 표)의 표들은 때가 겹치지 않는다. 때가 맞는 표가 없으면 조우가 없다.
         *     chance 가 0 이면 조우가 나지 않는 표다(마을처럼 안전한 곳). 그때는 몬스터를 적지 않는다.
         *     장소가 맵의 장소인지, 몬스터가 시트를 적은 몬스터인지는 게시할 때 본다.
         */
        "WanderTable-Output": {
            /** Chance */
            chance: number;
            /**
             * Monsters
             * @default []
             */
            monsters: components["schemas"]["WanderMonster-Output"][];
            /** Place Id */
            place_id?: string | null;
            /**
             * Times
             * @default []
             */
            times: components["schemas"]["TimeOfDay"][];
        };
        /**
         * WanderTableSnapshot
         * @description 무작위 조우 표 하나(#283). 판 안의 장소 항목 하나(place_id, 비우면 기본 표)에서 하루의 때(times, 비우면 언제나)에
         *     쓴다. 한 번 굴리면 chance% 로 조우가 나고, 나면 몬스터의 줄 하나를 몫대로 뽑는다.
         */
        WanderTableSnapshot: {
            /** Chance */
            chance: number;
            /**
             * Monsters
             * @default []
             */
            monsters: components["schemas"]["WanderMonsterSnapshot"][];
            /** Place Id */
            place_id?: string | null;
            /**
             * Times
             * @default []
             */
            times: components["schemas"]["TimeOfDay"][];
        };
        /**
         * WearRequest
         * @description 장비를 착용할 때 받는 값(#276). 가진 물건 하나를 규칙의 칸들에 끼운다.
         *
         *     slots 는 그 물건이 들어갈 수 있는 칸 중에서 차지하는 칸의 수만큼 고른다(CatalogItemOut.slots, slot_count).
         */
        WearRequest: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Slots */
            slots: string[];
        };
        /**
         * WhisperCreate
         * @description 쪽지를 보낼 때 받는 값. 보낸 사람은 토큰에서 읽는다. 입력으로 받지 않는다.
         */
        WhisperCreate: {
            /** Content */
            content: string;
            /**
             * Gm Visible
             * @default false
             */
            gm_visible: boolean;
            /**
             * Recipient Id
             * Format: uuid
             */
            recipient_id: string;
        };
        /**
         * WhisperNoticeUpdate
         * @description 쪽지를 보낸 사실을 알릴지 바꿀 때 받는 값. 칸을 빼먹으면 거부한다.
         */
        WhisperNoticeUpdate: {
            /** Whisper Notice */
            whisper_notice: boolean;
        };
        /**
         * WhisperOut
         * @description 자기 쪽지함의 쪽지 한 장.
         *
         *     보낸 것과 받은 것이 한 줄로 섞여 온다. sender_id 가 자기면 보낸 것이다.
         */
        WhisperOut: {
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Gm Visible */
            gm_visible: boolean;
            /** Recipient Character Name */
            recipient_character_name: string | null;
            /**
             * Recipient Id
             * Format: uuid
             */
            recipient_id: string;
            /** Round */
            round: number;
            /** Sender Character Name */
            sender_character_name: string | null;
            /**
             * Sender Id
             * Format: uuid
             */
            sender_id: string;
            /** Sequence */
            sequence: number;
        };
        /**
         * WhisperPage
         * @description 쪽지함의 한 쪽.
         */
        WhisperPage: {
            /** Items */
            items: components["schemas"]["WhisperOut"][];
            /** Last Sequence */
            last_sequence: number;
        };
        /**
         * WithdrawalResult
         * @description 답. 정리할 것이 없어도(이미 했다, 이 서버에 그 사람의 것이 없다) 같다. 인증 서버는 이것을 보고 그만 보낸다.
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
         * WorldCreate
         * @description 세계관을 만들 때 받는 값. 제목만 필수다.
         */
        WorldCreate: {
            /**
             * Description
             * @default
             */
            description: string;
            /**
             * Gm Notes
             * @default
             */
            gm_notes: string;
            /**
             * References Allowed
             * @default false
             */
            references_allowed: boolean;
            /**
             * Setting
             * @default
             */
            setting: string;
            /** Title */
            title: string;
        };
        /**
         * WorldDetail
         * @description 만든 사람이 자기 세계관을 볼 때의 값. gm_notes 까지 싣는다.
         *
         *     만든 사람이 아닌 사람에게 보여 주는 기능을 만들 때는 gm_notes 가 없는 응답을 따로 만든다.
         *     이 모양을 그대로 쓰면 비밀이 새어 나간다.
         */
        WorldDetail: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string;
            /** Gm Notes */
            gm_notes: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** References Allowed */
            references_allowed: boolean;
            /** Setting */
            setting: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            visibility: components["schemas"]["Visibility"];
        };
        /**
         * WorldSnapshot
         * @description 세계관.
         */
        WorldSnapshot: {
            /** Gm Notes */
            gm_notes: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * References Allowed
             * @default false
             */
            references_allowed: boolean;
            /** Setting */
            setting: string;
            /** Title */
            title: string;
        };
        /**
         * WorldUpdate
         * @description 세계관을 고칠 때 받는 값. 보낸 칸만 바꾼다.
         */
        WorldUpdate: {
            /** Description */
            description?: string | null;
            /** Gm Notes */
            gm_notes?: string | null;
            /** References Allowed */
            references_allowed?: boolean | null;
            /** Setting */
            setting?: string | null;
            /** Title */
            title?: string | null;
        };
        /**
         * WornOut
         * @description 착용한 물건 하나(#276). 무엇을 규칙의 어느 칸들에 끼웠는가. 이름은 판의 로어북 물건 항목의 이름이다.
         */
        WornOut: {
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /** Name */
            name: string;
            /** Slots */
            slots: string[];
        };
        /**
         * ItemThrowOut
         * @description 물건을 던진 결과(#277). 엔진이 정했다(app/rounds/throws.py). 던졌으면 판정의 결과가 함께 있다.
         */
        app__rounds__schemas__ItemThrowOut: {
            /** Ability */
            ability: string;
            /**
             * Cured
             * @default []
             */
            cured: components["schemas"]["CuredOut"][];
            /** Difficulty */
            difficulty: string;
            /**
             * Entry Id
             * Format: uuid
             */
            entry_id: string;
            /**
             * Injured
             * @default []
             */
            injured: components["schemas"]["InjuredOut"][];
            /** Name */
            name: string;
            /** Reason */
            reason: string | null;
            /** Remaining */
            remaining: number;
            /**
             * Resources
             * @default []
             */
            resources: components["schemas"]["ResourceShiftOut"][];
            target: components["schemas"]["ThrownAtOut"];
            /** Thrown */
            thrown: boolean;
        };
        /**
         * ItemThrowOut
         * @description 물건을 던지는 판정(#277). 능력치와 난이도(비면 rules 의 기본)다. 맞으면 그 물건의 효과(effects)가 든다(#801).
         *
         *     없는 물건도 던질 수 있다. 그때는 rules.item_check 로 던진다(그것도 없으면 던지지 못한다).
         */
        app__tables__schemas__ItemThrowOut: {
            /** Ability */
            ability: string;
            /** Difficulty */
            difficulty: string | null;
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
    read_scenario_api_v1_game_admin_scenarios__scenario_id__get: {
        parameters: {
            query: {
                reason: string;
            };
            header?: never;
            path: {
                scenario_id: string;
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
                    "application/json": components["schemas"]["ScenarioDetail"];
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
    sanction_scenario_api_v1_game_admin_scenarios__scenario_id__sanction_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SanctionOut"];
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
    read_version_api_v1_game_admin_scenarios__scenario_id__versions__number__get: {
        parameters: {
            query: {
                reason: string;
            };
            header?: never;
            path: {
                scenario_id: string;
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
    read_table_api_v1_game_admin_tables__table_id__get: {
        parameters: {
            query: {
                reason: string;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["OperatorTable"];
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
    end_table_api_v1_game_admin_tables__table_id__end_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OperatorTable"];
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
    read_events_api_v1_game_admin_tables__table_id__events_get: {
        parameters: {
            query: {
                reason: string;
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["EventPage"];
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
    read_messages_api_v1_game_admin_tables__table_id__messages_get: {
        parameters: {
            query: {
                reason: string;
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["MessagePage"];
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
    read_whispers_api_v1_game_admin_tables__table_id__whispers_get: {
        parameters: {
            query: {
                reason: string;
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["OperatorWhisperPage"];
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
    ban_publisher_api_v1_game_admin_users__user_id__publishing_ban_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublishingBanOut"];
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
    lift_ban_api_v1_game_admin_users__user_id__publishing_ban_lift_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ActionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PublishingBanOut"];
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
    list_bestiaries_api_v1_game_bestiaries_get: {
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
                    "application/json": components["schemas"]["AssetPage"];
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
    create_bestiary_api_v1_game_bestiaries_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BestiaryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssetSummary"];
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
    read_bestiary_api_v1_game_bestiaries__bestiary_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
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
                    "application/json": components["schemas"]["AssetSummary"];
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
    delete_bestiary_api_v1_game_bestiaries__bestiary_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
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
    update_bestiary_api_v1_game_bestiaries__bestiary_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BestiaryUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssetSummary"];
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
    list_monsters_api_v1_game_bestiaries__bestiary_id__monsters_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
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
                    "application/json": components["schemas"]["MonsterDetail"][];
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
    add_monster_api_v1_game_bestiaries__bestiary_id__monsters_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MonsterCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MonsterDetail"];
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
    copy_to_bestiary_api_v1_game_bestiaries__bestiary_id__monsters_copies_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReferenceCopy"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MonsterCopyResult"];
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
    delete_monster_api_v1_game_bestiaries__bestiary_id__monsters__monster_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
                monster_id: string;
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
    update_monster_api_v1_game_bestiaries__bestiary_id__monsters__monster_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                bestiary_id: string;
                monster_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MonsterUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MonsterDetail"];
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
    list_listings_api_v1_game_listings_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
                genre?: components["schemas"]["Genre"] | null;
                tag?: string | null;
                players?: number | null;
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
                    "application/json": components["schemas"]["PublicListingPage"];
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
    read_public_listing_api_v1_game_listings__scenario_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
                    "application/json": components["schemas"]["PublicListingDetail"];
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
    list_lorebooks_api_v1_game_lorebooks_get: {
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
                    "application/json": components["schemas"]["AssetPage"];
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
    create_lorebook_api_v1_game_lorebooks_post: {
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
                    "application/json": components["schemas"]["AssetSummary"];
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
    read_lorebook_api_v1_game_lorebooks__lorebook_id__get: {
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
                    "application/json": components["schemas"]["AssetSummary"];
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
    delete_lorebook_api_v1_game_lorebooks__lorebook_id__delete: {
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
    update_lorebook_api_v1_game_lorebooks__lorebook_id__patch: {
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
                    "application/json": components["schemas"]["AssetSummary"];
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
    list_entries_api_v1_game_lorebooks__lorebook_id__entries_get: {
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
                    "application/json": components["schemas"]["EntryDetail"][];
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
    add_entry_api_v1_game_lorebooks__lorebook_id__entries_post: {
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
                "application/json": components["schemas"]["EntryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntryDetail"];
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
    copy_to_lorebook_api_v1_game_lorebooks__lorebook_id__entries_copies_post: {
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
                "application/json": components["schemas"]["ReferenceCopy"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LoreCopyResult"];
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
    delete_entry_api_v1_game_lorebooks__lorebook_id__entries__entry_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
                entry_id: string;
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
    update_entry_api_v1_game_lorebooks__lorebook_id__entries__entry_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                lorebook_id: string;
                entry_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EntryUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EntryDetail"];
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
    read_me_api_v1_game_me_get: {
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
    list_personas_api_v1_game_personas_get: {
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
                    "application/json": components["schemas"]["PersonaPage"];
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
    create_persona_api_v1_game_personas_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PersonaWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaOut"];
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
    read_persona_api_v1_game_personas__persona_id__get: {
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
                    "application/json": components["schemas"]["PersonaOut"];
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
    update_persona_api_v1_game_personas__persona_id__put: {
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
                "application/json": components["schemas"]["PersonaWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PersonaOut"];
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
    delete_persona_api_v1_game_personas__persona_id__delete: {
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
    search_references_api_v1_game_references_get: {
        parameters: {
            query?: {
                q?: string;
                kind?: components["schemas"]["ReferenceKind"] | null;
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
                    "application/json": components["schemas"]["ReferencePage"];
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
    list_rulebooks_api_v1_game_rulebooks_get: {
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
                    "application/json": components["schemas"]["AssetPage"];
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
    create_rulebook_api_v1_game_rulebooks_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RulebookCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RulebookDetail"];
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
    list_templates_api_v1_game_rulebooks_templates_get: {
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
                    "application/json": components["schemas"]["TemplateList"];
                };
            };
        };
    };
    read_rulebook_api_v1_game_rulebooks__rulebook_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rulebook_id: string;
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
                    "application/json": components["schemas"]["RulebookDetail"];
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
    delete_rulebook_api_v1_game_rulebooks__rulebook_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rulebook_id: string;
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
    update_rulebook_api_v1_game_rulebooks__rulebook_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rulebook_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RulebookUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RulebookDetail"];
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
    list_scenarios_api_v1_game_scenarios_get: {
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
                    "application/json": components["schemas"]["ScenarioPage"];
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
    create_scenario_api_v1_game_scenarios_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScenarioCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScenarioDetail"];
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
    read_scenario_api_v1_game_scenarios__scenario_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
                    "application/json": components["schemas"]["ScenarioDetail"];
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
    delete_scenario_api_v1_game_scenarios__scenario_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
    update_scenario_api_v1_game_scenarios__scenario_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScenarioUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScenarioDetail"];
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
    read_listing_api_v1_game_scenarios__scenario_id__listing_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
                    "application/json": components["schemas"]["ListingDetail"];
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
    update_listing_api_v1_game_scenarios__scenario_id__listing_patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ListingUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListingDetail"];
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
    set_publication_api_v1_game_scenarios__scenario_id__listing_publication_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PublicationUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ListingDetail"];
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
    propose_monster_sheet_api_v1_game_scenarios__scenario_id__monsters__monster_id__sheet_proposal_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
                monster_id: string;
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
                    "application/json": components["schemas"]["MonsterSheetProposal"];
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
    check_publishable_api_v1_game_scenarios__scenario_id__publish_check_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
    list_versions_api_v1_game_scenarios__scenario_id__versions_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
    publish_scenario_api_v1_game_scenarios__scenario_id__versions_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
    read_version_api_v1_game_scenarios__scenario_id__versions__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                scenario_id: string;
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
    receive_withdrawal_api_v1_game_service_users__public_id__withdrawal_post: {
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
    list_tables_api_v1_game_tables_get: {
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
                    "application/json": components["schemas"]["TablePage"];
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
    create_table_api_v1_game_tables_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["TableCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    join_table_api_v1_game_tables_join_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JoinRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    list_lobby_api_v1_game_tables_lobby_get: {
        parameters: {
            query?: {
                scenario_id?: string | null;
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
                    "application/json": components["schemas"]["TablePage"];
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
    list_narration_models_api_v1_game_tables_narration_models_get: {
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
                    "application/json": components["schemas"]["NarrationModelsOut"];
                };
            };
        };
    };
    list_past_tables_api_v1_game_tables_past_get: {
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
                    "application/json": components["schemas"]["PastTablePage"];
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
    list_past_events_api_v1_game_tables_past__table_id__events_get: {
        parameters: {
            query?: {
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["EventPage"];
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
    download_past_transcript_api_v1_game_tables_past__table_id__transcript_get: {
        parameters: {
            query?: {
                format?: components["schemas"]["TranscriptFormat"];
            };
            header?: never;
            path: {
                table_id: string;
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
    read_table_api_v1_game_tables__table_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    set_character_api_v1_game_tables__table_id__character_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    bring_in_character_api_v1_game_tables__table_id__character_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    give_up_character_api_v1_game_tables__table_id__character_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    keep_character_api_v1_game_tables__table_id__character_persona_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
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
                    "application/json": components["schemas"]["PersonaOut"];
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
    roll_abilities_api_v1_game_tables__table_id__character_roll_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    get_clock_api_v1_game_tables__table_id__clock_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["ClockOut"];
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
    change_credit_wait_api_v1_game_tables__table_id__credit_wait_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreditWaitUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    end_table_api_v1_game_tables__table_id__end_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    wear_equipment_api_v1_game_tables__table_id__equipment_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WearRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    take_off_equipment_api_v1_game_tables__table_id__equipment__slot__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
                slot: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    list_events_api_v1_game_tables__table_id__events_get: {
        parameters: {
            query?: {
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["EventPage"];
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
    change_friendly_fire_api_v1_game_tables__table_id__friendly_fire_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FriendlyFireUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    transfer_host_api_v1_game_tables__table_id__host_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["HostTransfer"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    join_public_table_api_v1_game_tables__table_id__join_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LobbyJoinRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    leave_table_api_v1_game_tables__table_id__members_me_delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
    change_friendly_fire_consent_api_v1_game_tables__table_id__members_me_friendly_fire_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["FriendlyFireUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    kick_member_api_v1_game_tables__table_id__members__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    grant_reroll_api_v1_game_tables__table_id__members__user_id__reroll_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    list_messages_api_v1_game_tables__table_id__messages_get: {
        parameters: {
            query?: {
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["MessagePage"];
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
    post_message_api_v1_game_tables__table_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
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
    announce_typing_api_v1_game_tables__table_id__messages_typing_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
    change_narration_model_api_v1_game_tables__table_id__narration_model_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NarrationModelUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    change_narration_style_api_v1_game_tables__table_id__narration_style_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["NarrationStyleUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    change_references_api_v1_game_tables__table_id__references_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReferencesUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    change_round_time_limit_api_v1_game_tables__table_id__round_time_limit_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoundTimeLimitUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    list_rounds_api_v1_game_tables__table_id__rounds_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["RoundPage"];
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
    read_current_round_api_v1_game_tables__table_id__rounds_current_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["RoundOut"];
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
    close_round_api_v1_game_tables__table_id__rounds_current_close_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoundOut"];
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
    declare_api_v1_game_tables__table_id__rounds_current_declaration_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DeclarationUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoundOut"];
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
    read_scene_cast_api_v1_game_tables__table_id__rounds_current_people_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["SceneCastOut"];
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
    read_round_api_v1_game_tables__table_id__rounds__number__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["RoundOut"];
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
    read_round_charges_api_v1_game_tables__table_id__rounds__number__charges_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["ChargeOut"][];
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
    start_table_api_v1_game_tables__table_id__start_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["TableDetail"];
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
    open_stream_api_v1_game_tables__table_id__stream_get: {
        parameters: {
            query?: {
                events_after?: number;
                messages_after?: number;
                whispers_after?: number;
            };
            header?: {
                "last-event-id"?: string | null;
            };
            path: {
                table_id: string;
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
    download_transcript_api_v1_game_tables__table_id__transcript_get: {
        parameters: {
            query?: {
                format?: components["schemas"]["TranscriptFormat"];
            };
            header?: never;
            path: {
                table_id: string;
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
    change_whisper_notice_api_v1_game_tables__table_id__whisper_notice_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WhisperNoticeUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TableDetail"];
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
    list_whispers_api_v1_game_tables__table_id__whispers_get: {
        parameters: {
            query?: {
                after?: number;
                limit?: number;
            };
            header?: never;
            path: {
                table_id: string;
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
                    "application/json": components["schemas"]["WhisperPage"];
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
    post_whisper_api_v1_game_tables__table_id__whispers_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                table_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WhisperCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WhisperOut"];
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
    list_worlds_api_v1_game_worlds_get: {
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
                    "application/json": components["schemas"]["AssetPage"];
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
    create_world_api_v1_game_worlds_post: {
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
    read_world_api_v1_game_worlds__world_id__get: {
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
    delete_world_api_v1_game_worlds__world_id__delete: {
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
    update_world_api_v1_game_worlds__world_id__patch: {
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
