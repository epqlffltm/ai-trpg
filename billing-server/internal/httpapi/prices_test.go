// billing-server/internal/httpapi/prices_test.go

// 가격 목록(GET /service/prices)을 가짜 가격표와 실제 DB 로 확인한다.
package httpapi_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/httpapi"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/pricing"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/testenv"
)

const pricesURL = httpapi.APIPrefix + "/service/prices"

// fakeLister 는 정해 둔 목록으로 답하는 가짜 가격표다. 몇 번 불렸는지 센다.
type fakeLister struct {
	listings []pricing.Listing
	err      error
	calls    int
}

func (f *fakeLister) List(context.Context) ([]pricing.Listing, error) {
	f.calls++
	return f.listings, f.err
}

// aListing 은 지금 값과 다음 값이 있는 목록이다.
func aListing() []pricing.Listing {
	return []pricing.Listing{
		{Code: "narration.a.i0.o0", Current: &pricing.Price{Code: "narration.a.i0.o0", Credits: 120, Tier: pricing.TierStandard, Promo: true, Since: webhookNow},
			Next: &pricing.Scheduled{Credits: 240, OnSale: true, Tier: pricing.TierPremium, EffectiveAt: webhookNow.Add(24 * time.Hour)}},
		{Code: "narration.b.i0.o0", Current: &pricing.Price{Code: "narration.b.i0.o0", Credits: 30, Tier: pricing.TierPremium, Since: webhookNow},
			Next: &pricing.Scheduled{OnSale: false, Tier: pricing.TierPremium, EffectiveAt: webhookNow.Add(48 * time.Hour)}},
		{Code: "narration.c.i0.o0", Next: &pricing.Scheduled{Credits: 80, OnSale: true, Tier: pricing.TierBasic, Promo: true, EffectiveAt: webhookNow.Add(time.Hour)}},
	}
}

// priceDeps 는 가짜 가격표를 끼운 서버의 부품이다.
func priceDeps(lister httpapi.PriceLister) httpapi.Dependencies {
	return httpapi.Dependencies{Prices: lister, GameServerSecret: gameSecret, Now: func() time.Time { return webhookNow }}
}

// listAsGame 은 게임 서버가 서명해 가격 목록을 부른 것처럼 보낸다. headers 를 더 붙일 수 있다.
func listAsGame(t *testing.T, deps httpapi.Dependencies, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	all := serviceSigned(http.MethodGet, pricesURL, "")
	for name, value := range headers {
		all[name] = value
	}
	return send(t, deps, request{method: http.MethodGet, path: pricesURL, anonymous: true, headers: all})
}

func TestThePriceListGivesCurrentAndNextValues(t *testing.T) {
	response := listAsGame(t, priceDeps(&fakeLister{listings: aListing()}), nil)

	if response.Code != http.StatusOK {
		t.Fatalf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
	// 값은 글자다. 지금 팔지 않으면 credits, since, tier 가 null, 판매 중지 예약은 next.credits 와 next.tier 가 null 이다
	// 등급은 값과 함께 바뀔 수 있다(a 는 내일부터 premium)
	// a 의 지금 값은 행사가이고 내일 정가로 바뀐다. c 는 처음 팔 때부터 행사가다. 값이 없으면 promo 는 false 다
	want := `{"prices":[` +
		`{"code":"narration.a.i0.o0","credits":"120","since":"2026-03-02T09:00:00Z","tier":"standard","promo":true,"next":{"credits":"240","tier":"premium","promo":false,"effective_at":"2026-03-03T09:00:00Z"}},` +
		`{"code":"narration.b.i0.o0","credits":"30","since":"2026-03-02T09:00:00Z","tier":"premium","promo":false,"next":{"credits":null,"tier":null,"promo":false,"effective_at":"2026-03-04T09:00:00Z"}},` +
		`{"code":"narration.c.i0.o0","credits":null,"since":null,"tier":null,"promo":false,"next":{"credits":"80","tier":"basic","promo":true,"effective_at":"2026-03-02T10:00:00Z"}}]}`
	if body(response) != want {
		t.Errorf("본문 = %s\n기대 = %s", body(response), want)
	}
	if response.Header().Get("ETag") == "" || response.Header().Get("Cache-Control") != "no-cache" {
		t.Errorf("머리말 = %v", response.Header())
	}
}

func TestAnEmptyPriceListIsAnEmptyArray(t *testing.T) {
	response := listAsGame(t, priceDeps(&fakeLister{}), nil)

	if response.Code != http.StatusOK || body(response) != `{"prices":[]}` {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}

func TestTheSameListAnswersNotModifiedToItsETag(t *testing.T) {
	deps := priceDeps(&fakeLister{listings: aListing()})
	tag := listAsGame(t, deps, nil).Header().Get("ETag")

	for name, header := range map[string]string{
		"그대로": tag, "약한 비교": "W/" + tag, "여럿 가운데": `"other", ` + tag,
	} {
		response := listAsGame(t, deps, map[string]string{"If-None-Match": header})
		if response.Code != http.StatusNotModified || body(response) != "" || response.Header().Get("ETag") != tag {
			t.Errorf("%s: 상태 코드 = %d, 본문 = %q, ETag = %q", name, response.Code, body(response), response.Header().Get("ETag"))
		}
	}
}

func TestAChangedListGetsANewETagAndABody(t *testing.T) {
	lister := &fakeLister{listings: aListing()}
	deps := priceDeps(lister)
	old := listAsGame(t, deps, nil).Header().Get("ETag")

	lister.listings[0].Current.Credits = 150
	response := listAsGame(t, deps, map[string]string{"If-None-Match": old})

	if response.Code != http.StatusOK || response.Header().Get("ETag") == old || body(response) == "" {
		t.Errorf("상태 코드 = %d, ETag = %q(옛 %q)", response.Code, response.Header().Get("ETag"), old)
	}
}

func TestThePriceListNeedsTheGameServersSignature(t *testing.T) {
	lister := &fakeLister{listings: aListing()}
	deps := priceDeps(lister)
	cases := map[string]request{
		// 로그인한 사용자도 직접 부를 수 없다. 사용자에게는 게임 서버가 보여 준다
		"사용자의 토큰": {method: http.MethodGet, path: pricesURL},
		"서명 없음":   {method: http.MethodGet, path: pricesURL, anonymous: true},
		"다른 주소의 서명": {method: http.MethodGet, path: pricesURL, anonymous: true,
			headers: serviceSigned(http.MethodGet, holdsURL, "")},
	}
	for name, r := range cases {
		if response := send(t, deps, r); response.Code != http.StatusUnauthorized {
			t.Errorf("%s: 상태 코드 = %d", name, response.Code)
		}
	}
	if lister.calls != 0 {
		t.Errorf("가격표를 %d 번 읽었다. 서명이 틀리면 읽지 않아야 한다", lister.calls)
	}
}

func TestAFailedPriceListIsAServerError(t *testing.T) {
	response := listAsGame(t, priceDeps(&fakeLister{err: errors.New("relation price_versions does not exist")}), nil)

	if response.Code != http.StatusInternalServerError || strings.Contains(body(response), "price_versions") {
		t.Errorf("상태 코드 = %d, 본문 = %s. DB 의 오류를 싣지 않아야 한다", response.Code, body(response))
	}
}

func TestThePriceListWithTheRealDatabase(t *testing.T) {
	pool := testenv.Pool(t)
	services := realServices(t, pool, func() time.Time { return webhookNow })
	deps := httpapi.Dependencies{Prices: services.Prices, GameServerSecret: gameSecret, Now: func() time.Time { return webhookNow }}

	response := listAsGame(t, deps, nil)

	// 마이그레이션이 넣은 기본 서술 값이 들어 있다
	if response.Code != http.StatusOK || !strings.Contains(body(response), `{"code":"narration.standard","credits":"50"`) {
		t.Errorf("상태 코드 = %d, 본문 = %s", response.Code, body(response))
	}
}
