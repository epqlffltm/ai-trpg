-- docker/postgres/init/04-billing-role.sql
-- 결제 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(billing-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저)

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv billing_password BILLING_DB_PASSWORD

-- CREATEDB 를 주지 않는다. 결제 서버는 DB 를 새로 만들 일이 없다
CREATE ROLE billing LOGIN PASSWORD :'billing_password';

-- 결제 서버의 테이블이 놓일 스키마. 주문, 원장, 잔액이 여기에 놓인다.
-- 다른 서버의 계정에는 이 스키마의 권한을 주지 않는다. 잔액은 결제 서버의 API 로만 읽고 바꾼다
CREATE SCHEMA billing AUTHORIZATION billing;
