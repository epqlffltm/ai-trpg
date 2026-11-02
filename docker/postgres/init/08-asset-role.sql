-- docker/postgres/init/08-asset-role.sql
-- asset 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(asset-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저)

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv asset_password ASSET_DB_PASSWORD

-- CREATEDB 를 주지 않는다. 테스트용 DB 를 새로 만들지 않고, 같은 DB 의 다른 스키마를 쓴다
CREATE ROLE asset LOGIN PASSWORD :'asset_password';

-- 개발용 스키마. asset 서버의 테이블(페르소나, 캐릭터, 그림의 기록)이 여기에 놓인다.
-- 다른 서버의 계정에는 이 스키마의 권한을 주지 않는다. 다른 서버는 asset 서버의 API 로만 묻는다
CREATE SCHEMA asset AUTHORIZATION asset;

-- 테스트용 스키마. 테스트가 개발용 데이터를 건드리지 않게 따로 둔다
CREATE SCHEMA asset_test AUTHORIZATION asset;

-- 글자 조각 색인(03-extensions.sql 의 pg_trgm)의 연산자 묶음을 쓴다. 공개 목록의 이름 검색(#984).
-- 읽기(USAGE)만 준다. 색인을 만들 때 연산자 묶음을 스키마 이름으로 적어 부르므로 search_path 는 바꾸지 않는다
GRANT USAGE ON SCHEMA extensions TO asset;
