-- docker/postgres/init/09-chat-role.sql
-- chat 서버 전용 DB 계정과 스키마를 만든다.
--
-- 실행 시점: 데이터 볼륨이 비어 있는 첫 기동 때 한 번만 실행된다.
--           이미 데이터가 있는 볼륨에서는 직접 실행해야 한다(chat-server/README.md 참고).
-- 실행 주체: POSTGRES_USER (슈퍼유저)

-- 컨테이너 환경 변수에서 비밀번호를 읽어 psql 변수에 담는다
\getenv chat_password CHAT_DB_PASSWORD

-- CREATEDB 를 주지 않는다. 테스트용 DB 를 새로 만들지 않고, 같은 DB 의 다른 스키마를 쓴다
CREATE ROLE chat LOGIN PASSWORD :'chat_password';

-- 개발용 스키마. chat 서버의 테이블(가져온 캐릭터, 대화, 메시지, 요약과 기억)이 여기에 놓인다.
-- 다른 서버의 계정에는 이 스키마의 권한을 주지 않는다. 다른 서버는 chat 서버의 API 로만 묻는다
CREATE SCHEMA chat AUTHORIZATION chat;

-- 테스트용 스키마. 테스트가 개발용 데이터를 건드리지 않게 따로 둔다
CREATE SCHEMA chat_test AUTHORIZATION chat;

-- pgvector(03-extensions.sql 의 extensions 스키마)를 쓴다. 로어북 항목의 벡터를 저장하고 가까운 것을 찾는다(#672).
-- 읽기(USAGE)만 준다. chat 서버는 search_path 에 이 스키마를 더한다(chat-server/app/core/database.py)
GRANT USAGE ON SCHEMA extensions TO chat;
