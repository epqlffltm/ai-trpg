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

-- CREATEDB: Django 테스트 러너가 테스트용 DB(test_<이름>)를 만들고 지우는 데 필요하다
CREATE ROLE auth LOGIN CREATEDB PASSWORD :'auth_password';

-- 계정과 같은 이름의 스키마를 만든다.
-- PostgreSQL 의 기본 search_path 가 "$user", public 이라서
-- auth 계정으로 접속하면 별도 설정 없이 auth 스키마가 기본 스키마가 된다
CREATE SCHEMA auth AUTHORIZATION auth;
