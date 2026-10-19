// billing-server/cmd/fakegame/main_test.go

package main

import (
	"bytes"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/epqlffltm/ai-trpg/billing-server/internal/config"
	"github.com/epqlffltm/ai-trpg/billing-server/internal/serviceauth"
)

const (
	secret = "trpg-server-test-secret-of-32-chars"
	user   = "11111111-2222-4333-8444-555555555555"
)

// settingsFor 는 테스트 서버의 주소를 가리키는 설정을 만든다.
func settingsFor(t *testing.T, server *httptest.Server) config.Settings {
	t.Helper()
	host, portText, err := net.SplitHostPort(strings.TrimPrefix(server.URL, "http://"))
	port, portErr := strconv.Atoi(portText)
	if err != nil || portErr != nil {
		t.Fatalf("테스트 서버의 주소를 읽지 못했다: %s", server.URL)
	}
	return config.Settings{Host: host, Port: port, GameServerSecret: secret}
}

func TestParseBuildsEachRequest(t *testing.T) {
	cases := map[string]struct {
		args []string
		path string
		body map[string]string
	}{
		"hold":              {[]string{"hold", user, "table:1:round:3"}, "/api/v1/billing/service/holds", map[string]string{"user_id": user, "reference": "table:1:round:3", "price_code": "narration.standard"}},
		"hold 에 가격표 이름을 준다": {[]string{"hold", user, "table:1:round:3", "narration.premium"}, "/api/v1/billing/service/holds", map[string]string{"user_id": user, "reference": "table:1:round:3", "price_code": "narration.premium"}},
		"capture":           {[]string{"capture", "table:1:round:3"}, "/api/v1/billing/service/holds/capture", map[string]string{"reference": "table:1:round:3"}},
		"release":           {[]string{"release", "table:1:round:3"}, "/api/v1/billing/service/holds/release", map[string]string{"reference": "table:1:round:3"}},
		"extend":            {[]string{"extend", "table:1:round:3"}, "/api/v1/billing/service/holds/extend", map[string]string{"reference": "table:1:round:3"}},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			got, err := parse(tc.args)
			if err != nil || got.path != tc.path || len(got.body) != len(tc.body) {
				t.Fatalf("요청 = %+v, %v", got, err)
			}
			for key, want := range tc.body {
				if got.body[key] != want {
					t.Errorf("%s = %q, 기대 = %q", key, got.body[key], want)
				}
			}
		})
	}
}

func TestParseRejectsWrongCommands(t *testing.T) {
	cases := [][]string{
		nil,
		{"hold"},
		{"hold", user},
		{"hold", "not-a-uuid", "table:1:round:3"},
		{"hold", user, "table:1:round:3", "narration.standard", "extra"},
		{"capture"},
		{"capture", "table:1:round:3", "extra"},
		{"release"},
		{"extend"},
		{"extend", "table:1:round:3", "extra"},
		{"refund", "table:1:round:3"},
		{"prices", `"abc"`, "extra"},
	}
	for _, args := range cases {
		if _, err := parse(args); err == nil || !strings.Contains(err.Error(), "쓰는 법") {
			t.Errorf("%v: 오류 = %v. 쓰는 법을 보여 줘야 한다", args, err)
		}
	}
}

func TestSendSignsTheRequestTheWayTheServerChecksIt(t *testing.T) {
	sentAt := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	var verified error
	var method, contentType string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		method, contentType = r.Method, r.Header.Get("Content-Type")
		// 서버가 하는 것과 같은 확인이다(internal/httpapi/service.go)
		verified = serviceauth.Verify(secret, r.Header.Get(serviceauth.SignatureHeader), r.Method, r.URL.RequestURI(), raw, sentAt)
		w.WriteHeader(http.StatusCreated)
		_, _ = w.Write([]byte(`{"status":"held"}` + "\n"))
	}))
	defer server.Close()
	settings := settingsFor(t, server)
	request, err := parse([]string{"hold", user, "table:1:round:3"})
	if err != nil {
		t.Fatalf("명령을 읽지 못했다: %v", err)
	}
	var out bytes.Buffer

	err = send(settings, request, sentAt, &out)

	if err != nil || verified != nil {
		t.Fatalf("보내기 = %v, 서버의 서명 확인 = %v", err, verified)
	}
	if method != http.MethodPost || contentType != "application/json" || out.String() != "201 {\"status\":\"held\"}\n" {
		t.Errorf("메서드 = %s, Content-Type = %s, 적은 글 = %q", method, contentType, out.String())
	}
	// 비밀도 서명도 화면에 적지 않는다
	if strings.Contains(out.String(), secret) || strings.Contains(out.String(), "v1=") {
		t.Errorf("적은 글에 비밀이나 서명이 있다: %q", out.String())
	}
}

func TestSendSaysWhenTheServerIsNotUp(t *testing.T) {
	server := httptest.NewServer(http.NotFoundHandler())
	settings := settingsFor(t, server)
	server.Close()
	request, _ := parse([]string{"capture", "table:1:round:3"})

	err := send(settings, request, time.Now(), io.Discard)

	if err == nil || !strings.Contains(err.Error(), "서버가 떠 있는지") || strings.Contains(err.Error(), secret) {
		t.Errorf("오류 = %v", err)
	}
}

func TestPricesIsASignedGetWithTheLastETag(t *testing.T) {
	sentAt := time.Date(2026, 3, 2, 9, 0, 0, 0, time.UTC)
	var verified error
	var method, path, ifNoneMatch, contentType string
	var bodyLength int
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		raw, _ := io.ReadAll(r.Body)
		method, path, bodyLength = r.Method, r.URL.Path, len(raw)
		ifNoneMatch, contentType = r.Header.Get("If-None-Match"), r.Header.Get("Content-Type")
		verified = serviceauth.Verify(secret, r.Header.Get(serviceauth.SignatureHeader), r.Method, r.URL.RequestURI(), raw, sentAt)
		w.Header().Set("ETag", `"new"`)
		w.WriteHeader(http.StatusNotModified)
	}))
	defer server.Close()
	request, err := parse([]string{"prices", `"old"`})
	if err != nil {
		t.Fatalf("명령을 읽지 못했다: %v", err)
	}
	var out bytes.Buffer

	err = send(settingsFor(t, server), request, sentAt, &out)

	if err != nil || verified != nil {
		t.Fatalf("보내기 = %v, 서버의 서명 확인 = %v", err, verified)
	}
	if method != http.MethodGet || path != "/api/v1/billing/service/prices" || bodyLength != 0 || contentType != "" || ifNoneMatch != `"old"` {
		t.Errorf("메서드 = %s, 주소 = %s, 본문 %d 바이트, Content-Type = %q, If-None-Match = %q", method, path, bodyLength, contentType, ifNoneMatch)
	}
	if out.String() != "ETag \"new\"\n304 \n" {
		t.Errorf("적은 글 = %q", out.String())
	}

	plain, _ := parse([]string{"prices"})
	if plain.ifNoneMatch != "" || plain.body != nil {
		t.Errorf("ETag 없이 = %+v", plain)
	}
}
