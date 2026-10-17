// billing-server/internal/database/database.go

// Package database 는 PostgreSQL 연결 풀을 만들고, DB 가 살아 있는지 확인한다.
//
// 풀은 전역 변수로 두지 않는다. 만든 쪽(cmd/server)이 들고 있다가 필요한 곳에 넘기고, 끌 때 닫는다.
//
// 연결할 때마다 search_path 를 결제 서버의 스키마 하나로 맞춘다. 다른 스키마는 넣지 않는다.
// 다만 다른 서비스의 테이블을 막는 것은 search_path 가 아니라 DB 권한이다(docker/postgres/init/04-billing-role.sql).
// search_path 는 이름을 줄여 쓰게 해 줄 뿐이고, 스키마 이름을 붙여 쓰면 어디든 가리킬 수 있다.
//
// DB 에서 읽은 시각(timestamptz)은 UTC 로 받는다. 드라이버는 기본으로 그 PC 의 시간대로 바꿔 준다.
// 그러면 같은 시각이 서버를 띄운 PC 에 따라 응답에 "+09:00" 이나 "Z" 로 다르게 나간다.
//
// DB 가 스스로 끊는 시간(Limits)도 연결을 맺을 때 함께 보낸다(#296). 앱이 기다림을 그만두면 pgx 가 취소 요청을
// 보내지만, 앱이 죽으면(kill, OOM) 아무도 보내지 않는다. 그때 DB 는 잠금을 기다리던 쿼리를 그대로 쥐고 있다가,
// 잠금이 풀리면 끝까지 적는다. 그래서 끊는 일을 DB 에도 맡긴다.
package database

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ConnectTimeout 은 연결 하나를 맺을 때 기다리는 가장 긴 시간이다.
// DB 가 죽어 있을 때 요청이 하염없이 기다리지 않게 한다.
const ConnectTimeout = 5 * time.Second

// ErrInvalidURL 은 접속 주소를 읽지 못했다는 오류다.
// 드라이버의 오류를 그대로 올리지 않는다. 접속 주소에는 비밀번호가 들어 있다.
var ErrInvalidURL = errors.New("DATABASE_URL 을 읽지 못했습니다. postgres://계정:비밀번호@주소:포트/DB 모양인지 확인해 주세요")

// Limits 는 DB 가 스스로 쿼리를 끊는 시간들이다. 0 이면 그 설정을 보내지 않는다(PostgreSQL 의 기본, 끊지 않음).
// 값을 정한 근거는 README 의 설계 메모 "DB 도 스스로 끊는다" 에 잰 숫자와 함께 있다.
type Limits struct {
	// LockTimeout 은 행이나 테이블의 잠금을 기다리는 가장 긴 시간이다(lock_timeout). 넘으면 55P03 이다
	LockTimeout time.Duration
	// StatementTimeout 은 쿼리 하나의 가장 긴 시간이다(statement_timeout). 넘으면 57014 다
	StatementTimeout time.Duration
	// ClientCheckInterval 은 쿼리가 도는 동안 DB 가 클라이언트가 살아 있는지 보는 간격이다(client_connection_check_interval).
	// 클라이언트가 죽었으면 쿼리를 버린다. 잠금을 기다리는 동안에도 본다
	ClientCheckInterval time.Duration
}

var (
	// ServerLimits 는 서버(cmd/server)의 한도다. 요청 하나의 쿼리는 몇 밀리초에 끝난다.
	// 둘 다 결제 작업의 마감(order.OperationTimeout, 30초)보다 짧다. 마감 전에 DB 가 먼저 끊고 503 으로 답한다
	ServerLimits = Limits{LockTimeout: 5 * time.Second, StatementTimeout: 10 * time.Second, ClientCheckInterval: time.Second}
	// JobLimits 는 작업 명령(cmd/sweeper, cmd/reconcile, cmd/orders, cmd/prices)의 한도다.
	// 대사의 검사는 테이블 전체를 훑어 데이터가 늘수록 길어진다. 쿼리 하나는 길게 두고, 잠금은 서버와 같게 둔다
	JobLimits = Limits{LockTimeout: 5 * time.Second, StatementTimeout: 5 * time.Minute, ClientCheckInterval: time.Second}
)

// SQLSTATE 의 번호. DB 가 시간 제한으로 쿼리를 끊었을 때 오는 것이다.
const (
	// codeLockNotAvailable 은 lock_timeout 이 지났다는 뜻이다
	codeLockNotAvailable = "55P03"
	// codeQueryCanceled 는 statement_timeout 이 지났거나, 클라이언트가 취소를 요청했다는 뜻이다
	codeQueryCanceled = "57014"
)

// NewPoolConfig 는 접속 주소, 스키마, DB 의 한도로 연결 풀의 설정을 만든다. DB 에 연결하지 않는다.
// 한도는 접속 주소에 적힌 같은 설정보다 앞선다.
func NewPoolConfig(databaseURL string, schema string, limits Limits) (*pgxpool.Config, error) {
	poolConfig, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, ErrInvalidURL
	}
	poolConfig.ConnConfig.ConnectTimeout = ConnectTimeout
	// 연결이 맺어질 때 서버에 함께 보내는 설정이다. 연결마다 SET 을 따로 실행하지 않아도 된다
	poolConfig.ConnConfig.RuntimeParams["search_path"] = schema
	for name, value := range limits.runtimeParams() {
		poolConfig.ConnConfig.RuntimeParams[name] = value
	}
	poolConfig.AfterConnect = readTimesInUTC
	return poolConfig, nil
}

// runtimeParams 는 한도를 연결할 때 보내는 설정의 이름과 값으로 바꾼다. 0 인 것은 넣지 않는다.
func (l Limits) runtimeParams() map[string]string {
	params := map[string]string{}
	settings := map[string]time.Duration{
		"lock_timeout":                     l.LockTimeout,
		"statement_timeout":                l.StatementTimeout,
		"client_connection_check_interval": l.ClientCheckInterval,
	}
	for name, limit := range settings {
		// 1밀리초보다 짧은 값은 0ms(끊지 않음)가 되므로 보내지 않는다
		if milliseconds := limit.Milliseconds(); milliseconds > 0 {
			params[name] = fmt.Sprintf("%dms", milliseconds)
		}
	}
	return params
}

// IsTimeout 은 DB 가 시간 제한으로 쿼리를 끊었다는 오류인지 본다(lock_timeout, statement_timeout).
// 클라이언트가 보낸 취소(57014)도 같은 번호라 함께 걸린다. 어느 쪽이든 그 쿼리는 적히지 않았고, 다시 보내면 된다.
func IsTimeout(err error) bool {
	var pgErr *pgconn.PgError
	if !errors.As(err, &pgErr) {
		return false
	}
	return pgErr.Code == codeLockNotAvailable || pgErr.Code == codeQueryCanceled
}

// readTimesInUTC 는 연결 하나가 timestamptz 를 UTC 로 읽게 한다. 연결을 맺을 때마다 한 번 부른다.
// 가리키는 순간은 그대로다. 표기(시간대)만 정한다.
func readTimesInUTC(_ context.Context, conn *pgx.Conn) error {
	conn.TypeMap().RegisterType(&pgtype.Type{
		Name:  "timestamptz",
		OID:   pgtype.TimestamptzOID,
		Codec: &pgtype.TimestamptzCodec{ScanLocation: time.UTC},
	})
	return nil
}

// NewPool 은 연결 풀을 만든다. 만드는 것만으로는 DB 에 연결하지 않는다. 처음 쓸 때 연결한다.
// 그래서 DB 가 죽어 있어도 서버는 뜨고, 준비 상태 확인(/health/ready)이 그 사실을 알린다.
// limits 는 부르는 프로세스의 한도다(ServerLimits, JobLimits).
func NewPool(ctx context.Context, databaseURL string, schema string, limits Limits) (*pgxpool.Pool, error) {
	poolConfig, err := NewPoolConfig(databaseURL, schema, limits)
	if err != nil {
		return nil, err
	}
	return pgxpool.NewWithConfig(ctx, poolConfig)
}

// Pinger 는 DB 가 답하는지 물어볼 수 있는 것의 모양이다. *pgxpool.Pool 이 이 모양이다.
// 준비 상태 확인이 풀 전체가 아니라 이것만 받게 해서, 테스트가 가짜를 넣을 수 있다.
type Pinger interface {
	Ping(ctx context.Context) error
}
