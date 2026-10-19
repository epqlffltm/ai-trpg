// billing-server/internal/database/tracing_internal_test.go

package database

import (
	"context"
	"errors"
	"fmt"
	"testing"

	"github.com/jackc/pgx/v5/pgconn"
)

// 쿼리 span 의 이름과 상태를 DB 없이 본다.

func TestQueryNameReadsTheSqlcName(t *testing.T) {
	cases := map[string]string{
		"-- name: GetWallet :one\nSELECT 1":    "GetWallet",
		"-- name: ListHolds :many\r\nSELECT 1": "ListHolds",
		"-- name:\nSELECT 1":                   unnamedQuery,
		"SELECT 1":                             unnamedQuery,
		"  -- name: GetWallet :one":            unnamedQuery,
		"":                                     unnamedQuery,
	}
	for sql, want := range cases {
		if got := queryName(sql); got != want {
			t.Errorf("queryName(%q) = %q, 기대 = %q", sql, got, want)
		}
	}
}

func TestSQLStateIsTheCodeOnly(t *testing.T) {
	wrapped := fmt.Errorf("잔액을 줄이지 못했다: %w", &pgconn.PgError{Code: "23505", Message: "user-0b9f5e0c 이 이미 있다"})

	if got := sqlState(wrapped); got != "23505" {
		t.Errorf("sqlState = %q", got)
	}
	if got := sqlState(context.Canceled); got != "error" {
		t.Errorf("DB 가 낸 오류가 아닌 것 = %q", got)
	}
	if got := sqlState(errors.New("conn closed")); got != "error" {
		t.Errorf("DB 가 낸 오류가 아닌 것 = %q", got)
	}
}
