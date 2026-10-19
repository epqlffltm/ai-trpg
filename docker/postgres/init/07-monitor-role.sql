-- docker/postgres/init/07-monitor-role.sql
-- DB 의 메트릭을 읽는 계정(monitor)을 만든다(#25). 수집기(Alloy)의 PostgreSQL exporter 가 이 계정으로 붙는다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행한다(루트 README 의 "로그와 메트릭 모으기"). 다시 돌려도 된다.
-- 실행 주체: POSTGRES_USER (슈퍼유저)
--
-- 통계만 읽는다(pg_monitor). 서버들의 표는 읽지도 쓰지도 못한다. 스키마의 권한을 주지 않는다.
-- 루트 .env 의 MONITOR_DB_PASSWORD 가 비어 있으면 만들지 않는다. 메트릭(프로필 observability)을 쓰지 않는 PC 의 것이다.

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다. 변수가 없거나 비었으면 만들지 않는다
\getenv monitor_password MONITOR_DB_PASSWORD
\if :{?monitor_password}
SELECT length(:'monitor_password') > 0 AS create_monitor \gset
\else
\set create_monitor false
\endif

\if :create_monitor
-- 이미 있으면(직접 다시 돌렸다) 비밀번호만 맞춘다
SELECT NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'monitor') AS monitor_missing \gset
\if :monitor_missing
-- 연결은 셋까지다. Alloy 하나가 15초마다 붙는다. 새는 것이 있어도 서버들의 연결을 빼앗지 않는다
CREATE ROLE monitor LOGIN CONNECTION LIMIT 3 PASSWORD :'monitor_password';
\else
ALTER ROLE monitor PASSWORD :'monitor_password';
\endif
-- 통계와 설정을 읽는 내장 역할. 표의 내용은 읽지 못한다
GRANT pg_monitor TO monitor;
-- 읽기만 한다. 실수로 쓰는 문장을 보내도 DB 가 거절한다
ALTER ROLE monitor SET default_transaction_read_only = on;
-- 통계를 읽다 오래 걸리면 끊는다. 긁는 간격(15초)보다 짧다
ALTER ROLE monitor SET statement_timeout = '10s';
\else
\echo 'MONITOR_DB_PASSWORD 가 비어 있어 monitor 계정을 만들지 않는다'
\endif
