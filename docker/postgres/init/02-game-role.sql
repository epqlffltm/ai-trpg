-- docker/postgres/init/02-game-role.sql
-- 게임 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(game-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저)

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv game_password GAME_DB_PASSWORD

-- CREATEDB 를 주지 않는다. 테스트용 DB 를 새로 만들지 않고, 같은 DB 의 다른 스키마를 쓴다
CREATE ROLE game LOGIN PASSWORD :'game_password';

-- 개발용 스키마. 게임 서버의 테이블이 여기에 놓인다
CREATE SCHEMA game AUTHORIZATION game;

-- 테스트용 스키마. 테스트가 개발용 데이터를 건드리지 않게 따로 둔다
CREATE SCHEMA game_test AUTHORIZATION game;
