-- billing-server/migrations/00017_user_notices.sql
-- 사용자의 알림함에 보낼 일(#385). 알림 서버에 넣는다(notification-server).
--
-- 보호자 알림(00013)과 같은 방식이다. 결제를 끝내는 코드에서 적지 않고, 정리 작업이 한 바퀴마다 주문과 지급 묶음에서
-- 찾아 적는다. 결제를 끝내는 길(승인, 가상계좌의 입금, 대사, 운영자의 결정)이 여럿이라 한 곳에서 찾는 편이 빠뜨리지 않는다.
--
--   order.paid       결제가 끝났다(가상계좌는 입금되었을 때)
--   order.refunded   청약철회가 끝났다
--   credit.welcome   환영 크레딧을 받았다
--   credit.expiring  7일 안에 사라질 무료 크레딧이 있다. 사람마다 7일에 한 번이다
--
-- 같은 일은 source_key 로 한 번만 적는다. 알림 서버도 같은 열쇠를 한 번만 둔다.
-- 보낸 것(sent), 받지 않은 것(failed), 오래되어 보내지 않은 것(expired)은 30일 뒤에 지운다.
--
-- 스키마 이름을 붙이지 않는다. 같은 파일을 billing 과 billing_test 에 함께 쓴다.

-- +goose Up
CREATE TABLE user_notices (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- 알림 서버가 같은 알림을 알아보는 열쇠. "<kind>:<그 일의 번호>" 다
    source_key TEXT NOT NULL,
    user_id UUID NOT NULL,
    kind TEXT NOT NULL,
    -- 알림의 내용. 알림 서버가 사용자에게 그대로 내준다. 결제 대행사의 번호와 오류 글은 넣지 않는다
    payload JSONB NOT NULL,
    -- pending(보낼 것), sent(알림 서버가 받았다), failed(알림 서버가 받지 않았다. 버그다), expired(오래되어 보내지 않았다)
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    -- 이 시각부터 보낼 수 있다. 실패하면 뒤로 미룬다. 보내는 동안은 임대가 끝나는 시각이다
    next_attempt_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    CONSTRAINT user_notices_source_key_once UNIQUE (source_key),
    CONSTRAINT user_notices_kind_known CHECK (kind IN ('order.paid', 'order.refunded', 'credit.welcome', 'credit.expiring')),
    CONSTRAINT user_notices_status_known CHECK (status IN ('pending', 'sent', 'failed', 'expired')),
    CONSTRAINT user_notices_sent_at_matches_status CHECK ((status = 'sent') = (sent_at IS NOT NULL))
);

-- 정리 작업이 "보낼 때가 된 것"을 찾을 때 쓴다. 끝난 것은 색인에 넣지 않는다
CREATE INDEX user_notices_due ON user_notices (next_attempt_at) WHERE status = 'pending';

-- 사라질 크레딧을 알린 지 7일이 지났는지 사람마다 본다
CREATE INDEX user_notices_user_kind ON user_notices (user_id, kind, created_at);
-- 오래되어 보내지 않을 것과 30일이 지나 지울 것을 찾는다
CREATE INDEX user_notices_created_at ON user_notices (created_at);

-- 정리 작업이 최근의 환영 크레딧을 찾을 때 쓴다. 출석의 지급(attendance-…)은 날마다 생겨 많으므로 담지 않는다
CREATE INDEX free_grants_welcome_created_at ON free_grants (created_at) WHERE grant_key = 'welcome';

-- +goose Down
DROP INDEX free_grants_welcome_created_at;
DROP TABLE user_notices;
