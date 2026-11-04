# 이번 주 인기

첫 화면의 서비스마다의 랭킹 줄(#985). 최근 7일에 많이 시작한 작품부터 늘어놓는다.
카드의 수와 공개 목록의 인기순 정렬은 같은 이슈의 다음 PR 이다(공개 목록의 파일을 고쳐야 한다).

## 세는 것

| 작품 | 한 번 | 세는 서버 |
| --- | --- | --- |
| TRPG 시나리오 | 테이블을 연 것(끝난 테이블도 센다) | trpg-server(`game_tables`) |
| chat 캐릭터 | 대화를 시작한 것(지운 대화도 센다) | chat-server(`conversations`) |
| story 세계관 | 세션을 시작한 것(지운 세션도 센다) | story-server(`conversations`) |

같은 사람이 여러 번 시작하면 여러 번 센다(2026-11-04 유저 결정). 사람 수로 세면 부풀리기에 강하지만, 기간마다 사람을 가려 세야 해서 첫 판에서는 하지 않는다.

## 모으는 길

시나리오는 테이블이 같은 서버에 있어 랭킹을 읽을 때 바로 센다.

캐릭터와 세계관은 목록을 내는 asset-server 가 몇 분마다 chat 과 story 서버에서 통째로 받아 온다(2026-11-04 유저 결정).

```
asset-server ──(STATS_REFRESH_SECONDS 마다, 기본 한 시간)──▶ GET /api/v1/chat/service/stats/character-starts
             ──────────────────────────────────────────────▶ GET /api/v1/story/service/stats/world-starts
             ◀── {recent_days: 7, items: [{work_id, total, recent}]}
             → work_starts 의 그 종류의 줄을 통째로 바꾼다
```

- **서명.** 그 짝이 이미 나눈 비밀을 쓴다. asset 의 `CHAT_SERVER_SECRET` 은 chat 의 `ASSET_SECRET` 과 같은 값이다(story 도 같다). 서명은 주소까지 덮어 한쪽의 서명을 다른 쪽에 쓸 수 없다. 프록시는 `/api/v1/{chat,story}/service/` 를 밖에서 받지 않는다
- **통째로 받는 까닭.** 사건을 하나씩 보내면(발송함과 뒷일) 잃거나 두 번 보낸 것을 맞춰야 한다. 원본(대화의 표)에서 다시 세면 다시 받아도, 서버가 여럿이어도 같은 결과다. 대신 한 번에 작품 수만큼의 줄이 오간다. 작품이 수만이 되면 바뀐 것만 받는 길을 생각한다
- **요청의 길에서는 다른 서버를 부르지 않는다**([공용 코드 규칙의 원칙 2](shared-code.md#원칙)). 랭킹 API 는 쌓아 둔 수만 읽는다. chat 이나 story 가 죽으면 마지막에 받은 수가 그대로 나온다. 받지 못한 바퀴는 warning 을 남긴다
- 수는 한 시간까지 늦다(2026-11-04 유저 결정). TRPG 는 바로 바뀐다

## API

| 메서드 | 주소 | 하는 일 | 누가 |
| --- | --- | --- | --- |
| GET | `/api/v1/game/rankings/scenarios` | 시나리오의 랭킹 `{recent_days, items: [{rank, starts, listing}]}` | 누구나(로그인하지 않아도 된다) |
| GET | `/api/v1/asset/rankings/characters`, `/api/v1/asset/rankings/worlds` | 캐릭터와 세계관의 랭킹 `{recent_days, refreshed_at, items: [{rank, starts, character 또는 world}]}`. 한 번도 받지 못했으면 비어 있고 `refreshed_at` 이 `null` 이다 | 누구나 |
| GET | `/api/v1/chat/service/stats/character-starts`, `/api/v1/story/service/stats/world-starts` | 작품(asset 의 id)마다 모든 수와 최근 7일의 수. 시작한 적이 없는 것은 빠진다 | asset 서버의 서명 |

- 랭킹은 `limit`(1~20, 기본 10), `hide_adult`, `orientation` 을 받는다. 공개 목록의 조건(공개 중, 숨기지 않음, 링크 공개가 아님, 볼 수 있는 등급)과 보는 사람의 설정을 그대로 쓴다
- 순서는 최근 7일의 수, 같으면 모든 수, 그것도 같으면 최근에 공개한 것이다. 최근의 수가 0 인 것은 빠진다

## 설정(asset-server)

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `CHAT_URL`, `STORY_URL` | 비어 있음(받지 않음) | 수를 받아 오는 서버의 주소. compose 가 안쪽 주소를 넘긴다. 적으면 `CHAT_SERVER_SECRET`, `STORY_SERVER_SECRET` 도 있어야 뜬다 |
| `STATS_REFRESH_SECONDS` | `3600` | 받아 오는 간격(60~86400) |
| `STATS_TIMEOUT_SECONDS` | `10` | 한 번 받는 시간의 상한 |

## 화면

첫 화면(A1)의 "새로 공개된 …" 위에 "이번 주 인기 시나리오", "이번 주 인기 캐릭터", "이번 주 인기 세계관"을 둔다. 줄마다 1위부터 6개이고, 카드의 태그 앞에 순위와 수("1위", "이번 주 12.3K회")를 붙인다.
서버마다 따로 부르고 따로 실패한다(#593). 보는 사람의 설정이 바뀌면 다시 읽는다.

## 다음

- 공개 목록의 카드에 수를 싣고 인기순 정렬을 더한다(#985 의 나머지)
- 제작자 숫자 카드(#991)는 같은 수(`work_starts`, `game_tables`)를 다시 쓴다
