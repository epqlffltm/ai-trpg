// billing-server/internal/httpapi/wallet_test.go

package httpapi_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/auth"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/wallet"
)

const (
	walletURL  = httpapi.APIPrefix + "/wallet"
	entriesURL = httpapi.APIPrefix + "/wallet/entries"
)

// fakeWallet 은 정해 둔 대로 답하는 가짜 지갑이다. 무엇을 물어봤는지 적어 둔다.
type fakeWallet struct {
	balance wallet.Balance
	page    wallet.Page
	err     error

	users  []uuid.UUID
	before int64
	limit  int
	calls  int
}

func (f *fakeWallet) Balance(_ context.Context, userID uuid.UUID) (wallet.Balance, error) {
	f.calls++
	f.users = append(f.users, userID)
	return f.balance, f.err
}

func (f *fakeWallet) Entries(_ context.Context, userID uuid.UUID, before int64, limit int) (wallet.Page, error) {
	f.calls++
	f.users = append(f.users, userID)
	f.before, f.limit = before, limit
	return f.page, f.err
}

// asUser 는 userID 의 토큰을 가진 것처럼 GET 요청을 보낸다.
func asUser(t *testing.T, reader httpapi.WalletReader, userID string, path string) *httptest.ResponseRecorder {
	t.Helper()
	verifier := &fakeVerifier{claims: auth.Claims{UserID: mustUUID(t, userID)}}
	router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: verifier, Wallet: reader})
	request := httptest.NewRequest(http.MethodGet, path, nil)
	request.Header.Set("Authorization", "Bearer the-token")
	response := httptest.NewRecorder()
	router.ServeHTTP(response, request)
	return response
}

func TestWalletReturnsBothKindsAndTheirSum(t *testing.T) {
	reader := &fakeWallet{balance: wallet.Balance{Paid: 100, Free: 30}}

	response := asUser(t, reader, testenv.UserID, walletURL)

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
	// 양은 숫자가 아니라 글자로 나간다
	if got, want := body(response), `{"paid":"100","free":"30","total":"130"}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
	if len(reader.users) != 1 || reader.users[0].String() != testenv.UserID {
		t.Errorf("지갑에 물어본 사용자 = %v, 기대 = %s", reader.users, testenv.UserID)
	}
}

func TestWalletBelongsToTheTokenOwnerOnly(t *testing.T) {
	// 주소에 다른 사용자의 번호를 붙여도 토큰의 주인의 지갑만 읽는다
	const someoneElse = "11111111-2222-4333-8444-555555555555"
	reader := &fakeWallet{}

	for _, path := range []string{
		walletURL + "?user_id=" + someoneElse,
		entriesURL + "?user_id=" + someoneElse,
	} {
		if response := asUser(t, reader, testenv.UserID, path); response.Code != http.StatusOK {
			t.Errorf("%s 의 상태 코드 = %d", path, response.Code)
		}
	}
	for _, user := range reader.users {
		if user.String() != testenv.UserID {
			t.Errorf("지갑에 물어본 사용자 = %s, 기대 = %s", user, testenv.UserID)
		}
	}
	// 사용자 번호를 주소의 한 마디로 받는 주소도 없다
	if response := asUser(t, reader, testenv.UserID, walletURL+"/"+someoneElse); response.Code != http.StatusNotFound {
		t.Errorf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusNotFound)
	}
}

func TestWalletNeedsAToken(t *testing.T) {
	for _, path := range []string{walletURL, entriesURL} {
		reader := &fakeWallet{}
		router := httpapi.NewRouter(httpapi.Dependencies{DB: &fakeDB{}, Verifier: &fakeVerifier{}, Wallet: reader})
		response := httptest.NewRecorder()

		router.ServeHTTP(response, httptest.NewRequest(http.MethodGet, path, nil))

		assertUnauthorized(t, response)
		if reader.calls != 0 {
			t.Errorf("%s: 토큰이 없는데 지갑을 읽었다", path)
		}
	}
}

func TestWalletFailureIsAnInternalErrorWithoutTheCause(t *testing.T) {
	reader := &fakeWallet{err: errors.New(`relation "wallets" does not exist`)}

	for _, path := range []string{walletURL, entriesURL} {
		response := asUser(t, reader, testenv.UserID, path)

		if response.Code != http.StatusInternalServerError {
			t.Errorf("%s 의 상태 코드 = %d, 기대 = %d", path, response.Code, http.StatusInternalServerError)
		}
		// DB 의 오류는 응답에 싣지 않는다
		if strings.Contains(body(response), "wallets") || !strings.Contains(body(response), `"detail"`) {
			t.Errorf("%s 의 본문 = %s", path, body(response))
		}
	}
}

func TestEntriesReturnsLinesAndTheNextCursor(t *testing.T) {
	operation := mustUUID(t, "99999999-8888-4777-8666-555555555555")
	at := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	reader := &fakeWallet{page: wallet.Page{
		Entries: []wallet.Entry{
			{ID: 42, OperationID: operation, Kind: wallet.KindPaid, Reason: wallet.ReasonSpend, Amount: -20, CreatedAt: at},
			{ID: 41, OperationID: operation, Kind: wallet.KindFree, Reason: wallet.ReasonSpend, Amount: -30, CreatedAt: at},
		},
		NextBefore: 41,
	}}

	response := asUser(t, reader, testenv.UserID, entriesURL)

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
	}
	want := `{"entries":[` +
		`{"id":"42","operation_id":"99999999-8888-4777-8666-555555555555","kind":"paid","reason":"spend","amount":"-20","order_id":null,"hold_id":null,"created_at":"2026-03-02T09:00:00Z"},` +
		`{"id":"41","operation_id":"99999999-8888-4777-8666-555555555555","kind":"free","reason":"spend","amount":"-30","order_id":null,"hold_id":null,"created_at":"2026-03-02T09:00:00Z"}` +
		`],"next_before":"41"}`
	if got := body(response); got != want {
		t.Errorf("본문 = %s\n기대 = %s", got, want)
	}
}

func TestEntriesWithNothingIsAnEmptyListNotNull(t *testing.T) {
	// 서비스가 nil 을 돌려줘도 응답은 [] 다. 클라이언트가 null 을 따로 다루지 않아도 된다
	reader := &fakeWallet{page: wallet.Page{}}

	response := asUser(t, reader, testenv.UserID, entriesURL)

	if got, want := body(response), `{"entries":[],"next_before":null}`; got != want {
		t.Errorf("본문 = %s, 기대 = %s", got, want)
	}
}

func TestEntriesReadsTheRangeFromTheQuery(t *testing.T) {
	cases := []struct {
		name       string
		query      string
		wantBefore int64
		wantLimit  int
	}{
		{"적지 않으면 가장 최근부터 스무 줄", "", wallet.FirstPage, httpapi.DefaultPageSize},
		{"limit 만", "?limit=5", wallet.FirstPage, 5},
		{"before 만", "?before=41", 41, httpapi.DefaultPageSize},
		{"둘 다", "?before=41&limit=100", 41, 100},
		{"가장 작은 값", "?before=1&limit=1", 1, 1},
		{"가장 큰 before", "?before=9223372036854775807", wallet.FirstPage, httpapi.DefaultPageSize},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			reader := &fakeWallet{}

			response := asUser(t, reader, testenv.UserID, entriesURL+tc.query)

			if response.Code != http.StatusOK {
				t.Fatalf("상태 코드 = %d, 기대 = %d", response.Code, http.StatusOK)
			}
			if reader.before != tc.wantBefore || reader.limit != tc.wantLimit {
				t.Errorf("읽은 범위 = (%d, %d), 기대 = (%d, %d)", reader.before, reader.limit, tc.wantBefore, tc.wantLimit)
			}
		})
	}
}

func TestEntriesRejectsABadRangeBeforeReading(t *testing.T) {
	queries := []string{
		"?limit=0", "?limit=-1", "?limit=101", "?limit=many", "?limit=", "?limit=1.5",
		"?before=0", "?before=-1", "?before=abc", "?before=", "?before=9223372036854775808",
		"?before=41&limit=0",
	}
	for _, query := range queries {
		t.Run(query, func(t *testing.T) {
			reader := &fakeWallet{}

			response := asUser(t, reader, testenv.UserID, entriesURL+query)

			if response.Code != http.StatusBadRequest || !strings.Contains(body(response), `"detail"`) {
				t.Errorf("상태 코드 = %d, 본문 = %s. 400 이어야 한다", response.Code, body(response))
			}
			if reader.calls != 0 {
				t.Error("틀린 범위인데 지갑을 읽었다")
			}
		})
	}
}

func TestWalletWithTheRealDatabase(t *testing.T) {
	// 가짜를 끼우지 않고 실제 서비스와 DB 로 주소 둘을 끝까지 지난다
	pool := testenv.Pool(t)
	at := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	service := wallet.NewService(pool, func() time.Time { return at }, wallet.Policy{FreeFirst: true, FreeTTL: time.Hour})
	user := uuid.New()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	if err := errors.Join(
		service.Deposit(ctx, user, 100),
		service.GrantFree(ctx, user, 30),
		service.Spend(ctx, user, 50),
	); err != nil {
		t.Fatalf("크레딧을 준비하지 못했다: %v", err)
	}

	balance := asUser(t, service, user.String(), walletURL)
	if got, want := body(balance), `{"paid":"80","free":"0","total":"80"}`; balance.Code != http.StatusOK || got != want {
		t.Errorf("잔액 = %d %s, 기대 = 200 %s", balance.Code, got, want)
	}

	entries := asUser(t, service, user.String(), entriesURL+"?limit=3")
	var parsed struct {
		Entries []struct {
			Kind   string `json:"kind"`
			Reason string `json:"reason"`
			Amount string `json:"amount"`
		} `json:"entries"`
		NextBefore *string `json:"next_before"`
	}
	if err := json.Unmarshal(entries.Body.Bytes(), &parsed); err != nil || entries.Code != http.StatusOK {
		t.Fatalf("원장 = %d %s, %v", entries.Code, entries.Body.String(), err)
	}
	// 넉 줄 가운데 최근 석 줄이 오고, 한 줄이 더 있다고 알려 준다
	if len(parsed.Entries) != 3 || parsed.NextBefore == nil {
		t.Fatalf("원장 = %+v", parsed)
	}
	if first := parsed.Entries[0]; first.Kind != "paid" || first.Reason != "spend" || first.Amount != "-20" {
		t.Errorf("가장 최근 줄 = %+v, 기대 = {paid spend -20}", first)
	}

	rest := asUser(t, service, user.String(), entriesURL+"?limit=3&before="+*parsed.NextBefore)
	if got := body(rest); !strings.Contains(got, `"reason":"deposit","amount":"100"`) || !strings.HasSuffix(got, `"next_before":null}`) {
		t.Errorf("나머지 쪽 = %s", got)
	}
}
