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
package database

import (
	"context"
	"errors"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgtype"
	"github.com/jackc/pgx/v5/pgxpool"
)

// ConnectTimeout 은 연결 하나를 맺을 때 기다리는 가장 긴 시간이다.
// DB 가 죽어 있을 때 요청이 하염없이 기다리지 않게 한다.
const ConnectTimeout = 5 * time.Second

// ErrInvalidURL 은 접속 주소를 읽지 못했다는 오류다.
// 드라이버의 오류를 그대로 올리지 않는다. 접속 주소에는 비밀번호가 들어 있다.
var ErrInvalidURL = errors.New("DATABASE_URL 을 읽지 못했습니다. postgres://계정:비밀번호@주소:포트/DB 모양인지 확인해 주세요")

// NewPoolConfig 는 접속 주소와 스키마로 연결 풀의 설정을 만든다. DB 에 연결하지 않는다.
func NewPoolConfig(databaseURL string, schema string) (*pgxpool.Config, error) {
	poolConfig, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, ErrInvalidURL
	}
	poolConfig.ConnConfig.ConnectTimeout = ConnectTimeout
	// 연결이 맺어질 때 서버에 함께 보내는 설정이다. 연결마다 SET 을 따로 실행하지 않아도 된다
	poolConfig.ConnConfig.RuntimeParams["search_path"] = schema
	poolConfig.AfterConnect = readTimesInUTC
	return poolConfig, nil
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
func NewPool(ctx context.Context, databaseURL string, schema string) (*pgxpool.Pool, error) {
	poolConfig, err := NewPoolConfig(databaseURL, schema)
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
