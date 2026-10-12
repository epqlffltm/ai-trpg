-- docker/postgres/init/01-auth-role.sql
-- 인증 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 실행되지 않는다.
-- 실행 주체: POSTGRES_USER (슈퍼유저)
--
-- 왜 나누는가: 서버마다 자기 스키마만 쓸 수 있게 해서,
-- 다른 서버의 테이블을 직접 읽는 코드를 약속이 아니라 DB 권한으로 막는다.

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv auth_password AUTH_DB_PASSWORD
-- 테스트용 DB 를 만들 권한을 줄지. 개발과 CI 에서만 true 다. 적지 않으면 주지 않는다(#20)
\getenv allow_test_db AUTH_DB_ALLOW_TEST_DB

CREATE ROLE auth LOGIN PASSWORD :'auth_password';

-- CREATEDB: Django 테스트 실행기가 테스트용 DB(test_<이름>)를 만들고 지우는 데 필요하다.
-- 운영 계정에는 주지 않는다. 서버가 쓰지 않는 권한이고, 뚫렸을 때 DB 를 마음대로 만들 수 있게 된다.
-- 값은 true, false 같은 참거짓으로 적는다. 다른 값이면 psql 이 오류를 한 줄 찍고 주지 않는다(안전한 쪽)
\if :{?allow_test_db}
\if :allow_test_db
ALTER ROLE auth CREATEDB;
\endif
\endif

-- 계정과 같은 이름의 스키마를 만든다.
-- PostgreSQL 의 기본 search_path 가 "$user", public 이라서
-- auth 계정으로 접속하면 별도 설정 없이 auth 스키마가 기본 스키마가 된다
CREATE SCHEMA auth AUTHORIZATION auth;
