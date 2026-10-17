// billing-server/internal/migrate/migrate.go

// Package migrate 는 마이그레이션 파일(migrations 폴더)을 DB 에 적용하고 되돌린다.
//
// 적용하는 일은 goose 가 한다. 어느 파일까지 적용했는지는 goose 가 스키마 안의 표(goose_db_version)에 적는다.
// 이 패키지는 goose 를 결제 서버의 접속 방식에 맞춰 부르는 얇은 층이다.
//
// 서버가 뜰 때 저절로 적용하지 않는다. 테이블을 바꾸는 일은 사람이 명령으로 한다(cmd/migrate).
// 서버를 여러 대 띄울 때 저마다 테이블을 바꾸려 드는 일이 없고, 배포와 스키마 변경을 따로 되돌릴 수 있다.
package migrate

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"path"

	"github.com/jackc/pgx/v5/stdlib"
	"github.com/pressly/goose/v3"
	"github.com/pressly/goose/v3/lock"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/database"
	"github.com/epqlffltm/ai-trpg/billing-server/migrations"
)

// Step 은 마이그레이션 파일 하나와, 그것이 DB 에 적용되어 있는지다.
type Step struct {
	// Name 은 파일의 이름이다(00001_wallet_ledger.sql).
	Name string
	// Applied 는 이 파일이 DB 에 적용되어 있으면 true 다.
	Applied bool
}

// Up 은 아직 적용하지 않은 파일을 순서대로 모두 적용하고, 적용한 파일의 이름을 돌려준다.
// 이미 다 적용되어 있으면 빈 목록이다.
func Up(ctx context.Context, databaseURL string, schema string) ([]string, error) {
	var applied []string
	err := withProvider(databaseURL, schema, func(provider *goose.Provider) error {
		results, err := provider.Up(ctx)
		applied = names(results)
		return err
	})
	return applied, err
}

// Down 은 가장 마지막에 적용한 파일 하나를 되돌리고, 그 이름을 돌려준다.
// 되돌릴 것이 없으면 빈 글자다. 그 파일이 만든 테이블과 그 안의 데이터가 지워진다.
func Down(ctx context.Context, databaseURL string, schema string) (string, error) {
	var name string
	err := withProvider(databaseURL, schema, func(provider *goose.Provider) error {
		result, err := provider.Down(ctx)
		if errors.Is(err, goose.ErrNoNextVersion) {
			return nil
		}
		if err != nil {
			return err
		}
		name = path.Base(result.Source.Path)
		return nil
	})
	return name, err
}

// Status 는 파일마다 적용되어 있는지를 순서대로 돌려준다. DB 를 바꾸지 않는다.
func Status(ctx context.Context, databaseURL string, schema string) ([]Step, error) {
	var steps []Step
	err := withProvider(databaseURL, schema, func(provider *goose.Provider) error {
		statuses, err := provider.Status(ctx)
		for _, status := range statuses {
			steps = append(steps, Step{
				Name:    path.Base(status.Source.Path),
				Applied: status.State == goose.StateApplied,
			})
		}
		return err
	})
	return steps, err
}

// withProvider 는 DB 연결과 goose 를 준비해 run 에 넘기고, 끝나면 연결을 닫는다.
func withProvider(databaseURL string, schema string, run func(*goose.Provider) error) error {
	db, err := openDB(databaseURL, schema)
	if err != nil {
		return err
	}
	defer db.Close()

	provider, err := newProvider(db)
	if err != nil {
		return err
	}
	return run(provider)
}

// openDB 는 goose 가 쓰는 모양(database/sql)의 연결을 만든다. 서버의 연결 풀과 같은 설정을 쓴다.
// 그래서 search_path 가 같고, goose 가 만드는 표도 마이그레이션의 테이블도 schema 안에 놓인다.
// DB 의 한도는 두지 않는다(database.Limits{}). 데이터를 고쳐 쓰는 마이그레이션은 쿼리 하나가 길 수 있다.
func openDB(databaseURL string, schema string) (*sql.DB, error) {
	poolConfig, err := database.NewPoolConfig(databaseURL, schema, database.Limits{})
	if err != nil {
		return nil, err
	}
	return stdlib.OpenDB(*poolConfig.ConnConfig), nil
}

// newProvider 는 실행 파일에 담긴 마이그레이션 파일들을 읽는 goose 를 만든다.
func newProvider(db *sql.DB) (*goose.Provider, error) {
	// 두 곳에서 한꺼번에 적용하려 들면 한쪽이 기다린다. DB 의 잠금(advisory lock)을 쓴다.
	// 서버를 여러 대 배포하거나, 여러 패키지의 테스트가 함께 돌 때 같은 파일이 두 번 적용되지 않는다
	locker, err := lock.NewPostgresSessionLocker()
	if err != nil {
		return nil, fmt.Errorf("마이그레이션의 잠금을 준비하지 못했습니다: %w", err)
	}
	provider, err := goose.NewProvider(goose.DialectPostgres, db, migrations.Files, goose.WithSessionLocker(locker))
	if err != nil {
		return nil, fmt.Errorf("마이그레이션 파일을 읽지 못했습니다: %w", err)
	}
	return provider, nil
}

// names 는 적용한 결과에서 파일의 이름만 뽑는다.
func names(results []*goose.MigrationResult) []string {
	applied := make([]string, 0, len(results))
	for _, result := range results {
		applied = append(applied, path.Base(result.Source.Path))
	}
	return applied
}
