// billing-server/internal/txn/txn_test.go

package txn_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/jackc/pgx/v5"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/txn"
)

// 실제 PostgreSQL 에서 커밋과 되돌림에 맞춰 담긴 일이 불리는지 본다.

// ctx 는 시간 제한이 걸린 context 를 만든다.
func ctx(t *testing.T) context.Context {
	t.Helper()
	limited, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	t.Cleanup(cancel)
	return limited
}

// journal 은 불린 일을 차례로 적는다.
type journal []string

// hook 은 불리면 name 을 적는 일이다.
func (j *journal) hook(name string) func(context.Context) {
	return func(context.Context) { *j = append(*j, name) }
}

// put 은 tx 의 바구니에 이름이 name 인 일을 담는다. 담지 못하면 테스트를 멈춘다.
func (j *journal) put(t *testing.T, tx pgx.Tx, name string) {
	t.Helper()
	if !txn.AfterCommit(tx, j.hook(name+" committed"), j.hook(name+" rolled back")) {
		t.Fatal("txn.Run 으로 연 트랜잭션인데 담지 못했다")
	}
}

// want 는 적힌 것이 기대와 같은지 본다.
func (j journal) want(t *testing.T, want ...string) {
	t.Helper()
	if len(j) != len(want) {
		t.Fatalf("불린 일 = %v, 기대 = %v", j, want)
	}
	for i := range want {
		if j[i] != want[i] {
			t.Fatalf("불린 일 = %v, 기대 = %v", j, want)
		}
	}
}

func TestCommittedHooksRunInTheOrderTheyWerePut(t *testing.T) {
	var j journal

	err := txn.Run(ctx(t), testenv.Pool(t), func(tx pgx.Tx) error {
		j.put(t, tx, "first")
		j.put(t, tx, "second")
		// 커밋하기 전에는 아무것도 불리지 않는다
		j.want(t)
		_, err := tx.Exec(ctx(t), "SELECT 1")
		return err
	})

	if err != nil {
		t.Fatalf("오류 = %v", err)
	}
	j.want(t, "first committed", "second committed")
}

func TestAFailedTransactionRunsTheRollbackHooks(t *testing.T) {
	var j journal
	refused := errors.New("refused")

	err := txn.Run(ctx(t), testenv.Pool(t), func(tx pgx.Tx) error {
		j.put(t, tx, "deposit")
		return refused
	})

	if !errors.Is(err, refused) {
		t.Fatalf("오류 = %v. fn 의 오류가 그대로 와야 한다", err)
	}
	j.want(t, "deposit rolled back")
}

func TestATransactionTheDatabaseRefusedRunsTheRollbackHooks(t *testing.T) {
	// 문장이 실패하면 트랜잭션이 깨진다. fn 이 오류를 삼켜도 커밋은 되지 않는다
	var j journal

	err := txn.Run(ctx(t), testenv.Pool(t), func(tx pgx.Tx) error {
		j.put(t, tx, "spend")
		_, _ = tx.Exec(ctx(t), "SELECT 1 / 0")
		return nil
	})

	if err == nil {
		t.Fatal("깨진 트랜잭션을 커밋했다고 한다")
	}
	j.want(t, "spend rolled back")
}

func TestATransactionNotOpenedByRunCarriesNoBasket(t *testing.T) {
	var j journal

	err := pgx.BeginFunc(ctx(t), testenv.Pool(t), func(tx pgx.Tx) error {
		if txn.AfterCommit(tx, j.hook("committed"), j.hook("rolled back")) {
			t.Error("pgx.BeginFunc 로 연 트랜잭션에 담았다고 한다")
		}
		return nil
	})

	if err != nil {
		t.Fatalf("오류 = %v", err)
	}
	j.want(t)
}
