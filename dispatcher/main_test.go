package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/klauspost/compress/zstd"
)

func testRow(slug string) modelRow {
	value, _ := json.Marshal(slug)
	return modelRow{"slug": value}
}

func call(g http.Handler, method, path, body, token, primary string) *httptest.ResponseRecorder {
	r := httptest.NewRequest(method, path, strings.NewReader(body))
	r.Header.Set("X-Route-Token", "Bearer "+token)
	if primary != "" {
		r.Header.Set("Authorization", "Bearer "+primary)
		r.Header.Set("ChatGPT-Account-ID", "native-workspace")
	}
	w := httptest.NewRecorder()
	g.ServeHTTP(w, r)
	return w
}

func TestCredentialsDestinationsAndReferences(t *testing.T) {
	var mu sync.Mutex
	var catalogHits, nativeHits, routeHits int
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		if r.Header.Get("X-Route-Token") != "" || r.Header.Get("Authorization") != "Bearer native" || r.Header.Get("ChatGPT-Account-ID") != "native-workspace" {
			t.Error("wrong native credential boundary")
		}
		if r.URL.Path == "/models" {
			catalogHits++
			io.WriteString(w, `{"models":[{"slug":"gpt-6.2-sol","display_name":"Native","priority":30,"test_extension":123}]}`)
			return
		}
		nativeHits++
		if r.URL.Path != "/responses" {
			t.Error("wrong native endpoint")
		}
		io.WriteString(w, "ok")
	}))
	defer native.Close()
	route := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		routeHits++
		if r.Header.Get("X-Route-Token") != "" || r.Header.Get("Authorization") != "Bearer project" || r.Header.Get("ChatGPT-Account-ID") != "" {
			t.Error("wrong Route credential boundary")
		}
		var doc modelRow
		if err := json.NewDecoder(r.Body).Decode(&doc); err != nil || field(doc, "model") != "gpt-6.2-sol" {
			t.Error("incorrect outgoing model")
		}
		if r.URL.Path != "/responses/compact" || !strings.Contains(string(doc["input"]), "opaque-fixture") {
			t.Error("lost compaction path or opaque input")
		}
		w.WriteHeader(403)
		io.WriteString(w, "project refused")
	}))
	defer route.Close()
	g, err := newGateway(config{GatewayToken: "local", RouteKey: "project", NativeURL: native.URL, RouteURL: route.URL, Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	p := "/v1/models?client_version=1"
	if call(g, "GET", p, "", "invalid", "native").Code != 401 || call(g, "POST", "/v1/responses", `{"model":"route-gpt-6.2-sol"}`, "invalid", "native").Code != 401 {
		t.Fatal("invalid token was accepted")
	}
	only := call(g, "GET", p, "", "local", "")
	if only.Code != 200 || strings.Contains(only.Body.String(), "Native") || !strings.Contains(only.Body.String(), "route-gpt-6.2-sol") {
		t.Fatal("key-only catalog incorrect")
	}
	if catalogHits != 0 || nativeHits != 0 || routeHits != 0 {
		t.Fatal("contacted an upstream before authentication")
	}
	w := call(g, "GET", p, "", "local", "native")
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"test_extension":123`) || !strings.Contains(w.Body.String(), `"priority":31`) {
		t.Fatal("catalog metadata/order lost")
	}
	for _, body := range []string{`{"model":"route-unknown"}`, `{"model":"route-gpt-6.2-sol","previous_response_id":"resp_other"}`, `{"model":"route-gpt-6.2-sol","input":[{"type":"item_reference","id":"item_other"}]}`, `{"model":"route-gpt-6.2-sol","conversation":"conv_other"}`} {
		if call(g, "POST", "/v1/responses", body, "local", "native").Code != 400 {
			t.Fatal("invalid alias or account-bound reference accepted")
		}
	}
	w = call(g, "POST", "/v1/responses/compact", `{"model":"route-gpt-6.2-sol","input":[{"type":"compaction","encrypted_content":"opaque-fixture"}]}`, "local", "native")
	if w.Code != 403 || w.Body.String() != "project refused" {
		t.Fatal("failed to propagate upstream refusal")
	}
	if catalogHits != 1 || nativeHits != 0 || routeHits != 1 {
		t.Fatal("cross-account fallback or incorrect request count")
	}
	if call(g, "POST", "/v1/responses", `{"model":"gpt-6.2-sol"}`, "local", "native").Code != 200 || nativeHits != 1 {
		t.Fatal("native dispatch failed")
	}
}

func TestConcurrentStreamCancellation(t *testing.T) {
	started := make(chan struct{})
	cancelled := make(chan struct{})
	route := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/event-stream")
		io.WriteString(w, "data: {}\n\n")
		w.(http.Flusher).Flush()
		close(started)
		<-r.Context().Done()
		close(cancelled)
	}))
	defer route.Close()
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/models" {
			io.WriteString(w, `{"models":[{"slug":"gpt-6.2-sol"}]}`)
			return
		}
		io.WriteString(w, "native completed")
	}))
	defer native.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: route.URL, RouteKey: "project", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	call(g, "GET", "/v1/models?client_version=1", "", "local", "native")
	server := httptest.NewServer(g)
	defer server.Close()
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(ctx, "POST", server.URL+"/v1/responses", strings.NewReader(`{"model":"route-gpt-6.2-sol"}`))
	req.Header.Set("X-Route-Token", "Bearer local")
	res, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer res.Body.Close()
	<-started
	if w := call(g, "POST", "/v1/responses", `{"model":"gpt-6.2-sol"}`, "local", "native"); w.Code != 200 || w.Body.String() != "native completed" {
		t.Fatal("concurrent native request failed")
	}
	cancel()
	select {
	case <-cancelled:
	case <-time.After(2 * time.Second):
		t.Fatal("Stop did not cancel upstream")
	}
}

func TestImageToolUsesOriginatingTurn(t *testing.T) {
	var routeCount, nativeCount int
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		routeCount++
		if r.URL.Path != "/responses" || r.Header.Get("Authorization") != "Bearer project" || r.Header.Get("ChatGPT-Account-ID") != "" {
			t.Error("incorrect Route image destination")
		}
		var req struct {
			Model string
			Tools []struct{ Type, Model string }
		}
		if json.NewDecoder(r.Body).Decode(&req) != nil || req.Model != "gpt-6.2-sol" || len(req.Tools) != 1 || req.Tools[0].Type != "image_generation" || req.Tools[0].Model != "gpt-image-2" {
			t.Error("incorrect Responses image tool request")
		}
		io.WriteString(w, `{"status":"completed","created_at":1,"output":[{"type":"image_generation_call","status":"completed","id":"result","result":"aGVsbG8="}]}`)
	}))
	defer project.Close()
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		nativeCount++
		if r.URL.Path != "/images/generations" || r.Header.Get("Authorization") != "Bearer native" || r.Header.Get("X-Route-Token") != "" {
			t.Error("incorrect native image destination")
		}
		io.WriteString(w, "native")
	}))
	defer native.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: project.URL, RouteKey: "project", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	req := func(turn, account string) *http.Request {
		r := httptest.NewRequest("POST", "/v1/images/generations", strings.NewReader(`{"model":"gpt-image-2","prompt":"a test drawing"}`))
		r.Header.Set("X-Route-Token", "Bearer local")
		r.Header.Set("X-Codex-Image-Turn-Id", turn)
		r.Header.Set("Authorization", "Bearer "+account)
		return r
	}
	for id, model := range map[string]string{"turn-a": "route-gpt-6.2-sol", "turn-b": "gpt-6.2-sol"} {
		if !g.bindTurn(req(id, "native"), id, model, "1") {
			t.Fatal("turn binding failed")
		}
	}
	if g.bindTurn(req("turn-a", "native"), "turn-a", "gpt-6.2-sol", "1") {
		t.Fatal("rebound a live turn to a different billing account")
	}
	for _, sample := range []struct {
		turn, account string
		status        int
		replies       string
	}{
		{"turn-a", "native", 200, `"b64_json":"aGVsbG8="`}, {"turn-b", "native", 200, "native"},
		{"turn-a", "other", 409, "No billing account"}, {"missing", "native", 409, "No billing account"}} {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, req(sample.turn, sample.account))
		if w.Code != sample.status || !strings.Contains(w.Body.String(), sample.replies) {
			t.Errorf("incorrect image result for %s", sample.turn)
		}
	}
	if routeCount != 1 || nativeCount != 1 {
		t.Fatal("unexpected image upstream call count")
	}
}

func TestPrivateRotationPinsStreamAndRevokesAliases(t *testing.T) {
	started, release := make(chan struct{}), make(chan struct{})
	var once sync.Once
	finish := func() { once.Do(func() { close(release) }) }
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Error("unexpected native fallback") }))
	defer native.Close()
	var mu sync.Mutex
	var keys []string
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		key := r.Header.Get("Authorization")
		mu.Lock()
		keys = append(keys, key)
		mu.Unlock()
		if key == "Bearer original" {
			w.Header().Set("Content-Type", "text/event-stream")
			io.WriteString(w, "data: started\n\n")
			w.(http.Flusher).Flush()
			close(started)
			<-release
			io.WriteString(w, "data: finished\n\n")
			return
		}
		io.WriteString(w, "replacement")
	}))
	defer project.Close()
	g, err := newGateway(config{NativeURL: native.URL, RouteURL: project.URL, RouteKey: "original", GatewayToken: "local", Catalogs: map[string][]modelRow{"1": {testRow("route-gpt-6.2-sol"), testRow("route-gpt-6.2-astra")}}})
	if err != nil {
		t.Fatal(err)
	}
	d := &dispatcher{}
	d.active.Store(g)
	server := httptest.NewServer(d)
	defer server.Close()
	defer finish()
	body := `{"model":"route-gpt-6.2-sol"}`
	req, _ := http.NewRequest("POST", server.URL+"/v1/responses", strings.NewReader(body))
	req.Header.Set("X-Route-Token", "Bearer local")
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	resp, err := http.DefaultClient.Do(req.WithContext(ctx))
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	<-started
	update := `{"RouteKey":"new","Catalogs":{"1":[{"slug":"route-gpt-6.2-sol"}]}}`
	if call(d, "POST", "/replace", update, "local", "").Code != 404 {
		t.Fatal("control path exposed on data socket")
	}
	w := httptest.NewRecorder()
	d.control(w, httptest.NewRequest("POST", "/replace", strings.NewReader(update)))
	if w.Code != 204 {
		t.Fatal("private control rejected rotation")
	}
	if call(d, "POST", "/v1/responses", `{"model":"route-gpt-6.2-astra"}`, "local", "").Code != 400 {
		t.Fatal("revoked alias still accepted")
	}
	if got := call(d, "POST", "/v1/responses", body, "local", ""); got.Code != 200 || got.Body.String() != "replacement" {
		t.Fatal("new request did not use replacement key")
	}
	finish()
	all, err := io.ReadAll(resp.Body)
	if err != nil || !strings.Contains(string(all), "finished") {
		t.Fatal("rotation broke active stream")
	}
	mu.Lock()
	defer mu.Unlock()
	if len(keys) != 2 || keys[0] != "Bearer original" || keys[1] != "Bearer new" {
		t.Fatal("unexpected billed requests")
	}
}

func TestRefreshForNewClientVersion(t *testing.T) {
	if os.Getenv("ROUTE_TEST_CATALOG_CHILD") == "1" {
		if os.Args[len(os.Args)-1] != "0.172.0" {
			os.Exit(2)
		}
		fmt.Print(`[{"slug":"route-gpt-6.2-sol"}]`)
		os.Exit(0)
	}
	t.Setenv("ROUTE_TEST_CATALOG_CHILD", "1")
	g, err := newGateway(config{GatewayToken: "token", RouteKey: "route", NativeURL: "https://chatgpt.com/backend-api/codex", RouteURL: "https://api.openai.com/v1", Catalogs: map[string][]modelRow{"0.171.0": {}}, CatalogCommand: []string{os.Args[0], "-test.run=^TestRefreshForNewClientVersion$", "--"}})
	if err != nil {
		t.Fatal(err)
	}
	d := &dispatcher{}
	d.active.Store(g)
	path := "/v1/models?client_version=0.172.0-alpha.1"
	if r := call(d, "GET", path, "", "bad", ""); r.Code != 401 || d.active.Load() != g {
		t.Fatal("unauthorized refresh")
	}
	if r := call(d, "GET", path, "", "token", ""); r.Code != 200 || !strings.Contains(r.Body.String(), "route-gpt-6.2-sol") {
		t.Fatalf("refresh failed: %d %s", r.Code, r.Body)
	}
	refreshed := d.active.Load()
	if refreshed == g || refreshed.routingState != g.routingState || !refreshed.eligibleAlias("0.172.0", "route-gpt-6.2-sol") {
		t.Fatal("routing snapshot")
	}
	call(d, "GET", path, "", "token", "")
	if d.active.Load() != refreshed {
		t.Fatal("unexpected duplicate refresh")
	}

	// A resumed chat can make a Responses request before fetching a fresh catalog.
	d.active.Store(g)
	r := httptest.NewRequest(http.MethodPost, "/v1/responses", strings.NewReader(`{"model":"route-gpt-6.2-astra"}`))
	r.Header.Set("X-Route-Token", "Bearer token")
	r.Header.Set("User-Agent", "codex_cli_rs/0.172.0 (Mac OS; arm64)")
	w := httptest.NewRecorder()
	d.ServeHTTP(w, r)
	if w.Code != 400 || !strings.Contains(w.Body.String(), "Unknown or revoked Route model") || d.active.Load() == g {
		t.Fatalf("response did not refresh the requesting client's catalog: %d %s", w.Code, w.Body)
	}
}

func TestResponsesUsesClientUserAgentVersion(t *testing.T) {
	native := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer native" {
			t.Error("native backend did not receive its own credential")
		}
		if r.URL.Path == "/models" {
			if r.URL.Query().Get("client_version") != "0.171.0" {
				t.Errorf("native catalog used %s", r.URL.RawQuery)
			}
			io.WriteString(w, `{"models":[{"slug":"gpt-6.2-sol"}]}`)
			return
		}
		io.WriteString(w, "native")
	}))
	defer native.Close()
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body modelRow
		if r.Header.Get("Authorization") != "Bearer project" ||
			json.NewDecoder(r.Body).Decode(&body) != nil || field(body, "model") != "gpt-6.2-sol" {
			t.Error("project backend did not receive its credential and unaliased model")
		}
		io.WriteString(w, "project")
	}))
	defer project.Close()
	g, err := newGateway(config{GatewayToken: "token", RouteKey: "project", NativeURL: native.URL,
		RouteURL: project.URL, Catalogs: map[string][]modelRow{"0.171.0": {}, "0.172.0": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct{ agent, model, want string }{
		{"Codex Desktop/0.171.0-alpha.13 (Mac OS; arm64)", "gpt-6.2-sol", "native"},
		{"codex_cli_rs/0.172.0 (Mac OS; arm64)", "route-gpt-6.2-sol", "project"},
	} {
		r := httptest.NewRequest(http.MethodPost, "/v1/responses", strings.NewReader(fmt.Sprintf(`{"model":%q}`, tc.model)))
		r.Header.Set("X-Route-Token", "Bearer token")
		r.Header.Set("Authorization", "Bearer native")
		r.Header.Set("User-Agent", tc.agent)
		w := httptest.NewRecorder()
		g.ServeHTTP(w, r)
		if w.Code != 200 || w.Body.String() != tc.want {
			t.Errorf("%s: got %d %s, want 200 from %s", tc.model, w.Code, w.Body, tc.want)
		}
	}
}

func TestNativeProviderAuthenticationAndCompression(t *testing.T) {
	authFile := filepath.Join(t.TempDir(), "auth.json")
	writeAuth := func(token string) {
		t.Helper()
		if err := os.WriteFile(authFile, fmt.Appendf(nil, `{"tokens":{"access_token":%q,"account_id":"account"}}`, token), 0600); err != nil {
			t.Fatal(err)
		}
	}
	writeAuth("chatgpt")
	project := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("Authorization") != "Bearer project" || r.Header.Get("ChatGPT-Account-ID") != "" || r.Header.Get("Content-Encoding") != "" {
			t.Error("native credential or encoding leaked to the project request")
		}
		var body modelRow
		if json.NewDecoder(r.Body).Decode(&body) != nil || field(body, "model") != "gpt-6.2-sol" || field(body, "input") != "context from native chat" {
			t.Error("project request lost the model or conversation input")
		}
		io.WriteString(w, "project")
	}))
	defer project.Close()
	g, err := newGateway(config{GatewayToken: "local", RouteKey: "project", NativeAuthFile: authFile,
		NativeURL: "https://chatgpt.com/backend-api/codex", RouteURL: project.URL,
		Catalogs: map[string][]modelRow{"0.171.0": {testRow("route-gpt-6.2-sol")}}})
	if err != nil {
		t.Fatal(err)
	}
	send := func(r *http.Request, token, account string) *httptest.ResponseRecorder {
		r.Header.Set("Authorization", "Bearer "+token)
		r.Header.Set("ChatGPT-Account-ID", account)
		w := httptest.NewRecorder()
		g.ServeHTTP(w, r)
		return w
	}
	ws := httptest.NewRequest(http.MethodGet, "/v1/responses", nil)
	ws.Header.Set("Upgrade", "websocket")
	if got := send(ws, "chatgpt", "account").Code; got != http.StatusUpgradeRequired {
		t.Fatalf("WebSocket should negotiate HTTP fallback, got %d", got)
	}
	encoder, err := zstd.NewWriter(nil)
	if err != nil {
		t.Fatal(err)
	}
	defer encoder.Close()
	data := encoder.EncodeAll([]byte(`{"model":"route-gpt-6.2-sol","input":"context from native chat"}`), nil)
	post := func(token, account string, want int) {
		t.Helper()
		r := httptest.NewRequest(http.MethodPost, "/v1/responses", bytes.NewReader(data))
		r.Header.Set("Content-Encoding", "zstd")
		r.Header.Set("Version", "0.171.0-alpha.13")
		w := send(r, token, account)
		if w.Code != want || (want == 200 && w.Body.String() != "project") {
			t.Fatalf("wanted %d, got %d %s", want, w.Code, w.Body)
		}
	}
	post("chatgpt", "other-account", 401)
	post("chatgpt", "account", 200)
	writeAuth("new-chatgpt")
	post("chatgpt", "account", 401)
	post("new-chatgpt", "account", 200)
}
