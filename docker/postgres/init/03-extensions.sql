-- docker/postgres/init/03-extensions.sql
-- 확장(extension)을 둘 스키마를 만들고 pgvector 와 pg_trgm 을 켠다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(trpg-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저). 확장은 슈퍼유저만 켤 수 있다.
--
-- 왜 따로 두는가: 확장은 데이터베이스마다 한 번, 스키마 하나에만 놓인다.
-- game 과 game_test 는 같은 데이터베이스의 두 스키마라 어느 한쪽에 둘 수 없다.
-- 확장 전용 스키마에 두고, 쓰는 계정에게 읽기(USAGE)만 준다. 게임 서버는 search_path 에 이 스키마를 더한다.

CREATE SCHEMA IF NOT EXISTS extensions;

-- 벡터 타입(vector)과 거리 연산자(<=> 등). 로어북 항목의 임베딩을 저장하고 가까운 것을 찾는 데 쓴다
CREATE EXTENSION IF NOT EXISTS vector SCHEMA extensions;

-- 글자 조각(trigram) 색인과 그 연산자. 공개 목록의 이름·소개 검색(ILIKE)을 빠르게 한다(#984).
-- 게임 서버(시나리오)와 asset 서버(캐릭터, 세계관)가 쓴다. asset 계정의 읽기는 08-asset-role.sql 에서 준다
CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA extensions;

-- 게임 서버만 쓴다. 인증 서버에는 주지 않는다
GRANT USAGE ON SCHEMA extensions TO game;
