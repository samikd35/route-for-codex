// The combined-provider proof runs in a private directory and receives credentials on stdin.
package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

const catalogLimit = 16 << 20
const inputLimit = 128 << 20

type modelRow map[string]json.RawMessage

func field(row modelRow, name string) string {
	var value string
	_ = json.Unmarshal(row[name], &value)
	return value
}

type config struct {
	Socket, Lease, GatewayToken, RouteKey string
	NativeURL, RouteURL                   string
	// The proof stages one catalog per installed client version.
	Catalogs map[string][]modelRow
}

type gateway struct {
	config        config
	native, route *url.URL
	client        *http.Client
	*routingState
}

type routingState struct {
	mu sync.RWMutex
	// Scoped to the native credential, workspace, and requesting client version.
	nativeModels map[[32]byte]nativeCatalogEntry
	turns        map[[32]byte]turnBinding
}

func destination(value, approved string) (*url.URL, error) {
	u, err := url.Parse(value)
	if err != nil || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return nil, errors.New("invalid upstream URL")
	}
	if value == approved || (u.Scheme == "http" && u.Hostname() == "127.0.0.1" && u.Port() != "") {
		return u, nil
	}
	return nil, errors.New("unsupported upstream destination")
}

func newGateway(c config) (*gateway, error) {
	if c.GatewayToken == "" || c.RouteKey == "" || len(c.Catalogs) == 0 {
		return nil, errors.New("missing credentials or catalog")
	}
	for version, rows := range c.Catalogs {
		if version == "" {
			return nil, errors.New("missing catalog version")
		}
		seen := make(map[string]bool, len(rows))
		for _, row := range rows {
			slug := field(row, "slug")
			if !strings.HasPrefix(slug, "route-gpt-") || seen[slug] {
				return nil, errors.New("invalid or duplicate Route alias")
			}
			seen[slug] = true
		}
	}
	n, err := destination(c.NativeURL, "https://chatgpt.com/backend-api/codex")
	if err != nil {
		return nil, err
	}
	r, err := destination(c.RouteURL, "https://api.openai.com/v1")
	if err != nil {
		return nil, err
	}
	return &gateway{config: c, native: n, route: r,
		routingState: &routingState{turns: make(map[[32]byte]turnBinding), nativeModels: make(map[[32]byte]nativeCatalogEntry)},
		client:       &http.Client{CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }},
	}, nil
}

func nativeHeaders(in, out http.Header) {
	for _, key := range []string{"Authorization", "ChatGPT-Account-ID", "User-Agent", "Originator", "OpenAI-Beta", "Version", "Session_id", "Thread_id", "X-Codex-Turn-Metadata", "X-Codex-Image-Turn-Id", "X-Codex-Installation-Id"} {
		if value := in.Get(key); value != "" {
			out.Set(key, value)
		}
	}
}

func identity(r *http.Request, version string) [32]byte {
	return sha256.Sum256([]byte(r.Header.Get("Authorization") + "\x00" + r.Header.Get("ChatGPT-Account-ID") + "\x00" + version))
}

func reject(w http.ResponseWriter, status int, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"error": map[string]string{"message": message}})
}

type nativeCatalogEntry struct {
	slugs   map[string]bool
	expires time.Time
}

func (g *gateway) nativeCatalog(r *http.Request, version string) ([]modelRow, error) {
	if r.Header.Get("Authorization") == "" {
		return nil, nil
	}
	target := *g.native
	target.Path += "/models"
	target.RawQuery = url.Values{"client_version": {version}}.Encode()
	ctx, cancel := context.WithTimeout(r.Context(), 20*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, "GET", target.String(), nil)
	if err != nil {
		return nil, errors.New("Invalid native catalog endpoint")
	}
	nativeHeaders(r.Header, req.Header)
	res, err := g.client.Do(req)
	if err != nil {
		return nil, errors.New("Native catalog unavailable")
	}
	defer res.Body.Close()
	var payload struct{ Models []modelRow }
	switch res.StatusCode {
	case 200:
		data, err := io.ReadAll(io.LimitReader(res.Body, catalogLimit+1))
		if err != nil || len(data) > catalogLimit || json.Unmarshal(data, &payload) != nil || payload.Models == nil {
			return nil, errors.New("Invalid native catalog")
		}
	case 401, 403:
		// This account cannot contribute native models to the picker.
	default:
		return nil, errors.New("Native catalog unavailable")
	}
	known := make(map[string]bool, len(payload.Models))
	for _, row := range payload.Models {
		slug := field(row, "slug")
		if slug == "" || strings.HasPrefix(slug, "route-") || known[slug] {
			return nil, errors.New("Native model ID conflicts with the combined catalog")
		}
		known[slug] = true
	}
	now := time.Now()
	g.mu.Lock()
	for key, entry := range g.nativeModels {
		if now.After(entry.expires) {
			delete(g.nativeModels, key)
		}
	}
	g.nativeModels[identity(r, version)] = nativeCatalogEntry{known, now.Add(5 * time.Minute)}
	g.mu.Unlock()
	return payload.Models, nil
}

func (g *gateway) catalog(w http.ResponseWriter, r *http.Request) {
	version := r.URL.Query().Get("client_version")
	rows, ok := g.config.Catalogs[version]
	if !ok {
		reject(w, 409, "No Route catalog for this Codex version")
		return
	}
	native, err := g.nativeCatalog(r, version)
	if err != nil {
		reject(w, 502, err.Error())
		return
	}
	maxPriority := 0
	for _, row := range native {
		var priority int
		if json.Unmarshal(row["priority"], &priority) == nil && priority > maxPriority {
			maxPriority = priority
		}
	}
	combined := append([]modelRow{}, native...)
	for i, row := range rows {
		copyRow := make(modelRow, len(row))
		for k, v := range row {
			copyRow[k] = v
		}
		copyRow["priority"], _ = json.Marshal(maxPriority + i + 1)
		combined = append(combined, copyRow)
	}
	w.Header().Set("Cache-Control", "private, no-store")
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]any{"models": combined})
}

// Account-scoped IDs cannot be resolved by a different upstream. Tool call IDs
// and inline encrypted items are ordinary replay input and must reach the selected upstream intact.
func hasServerReference(fields modelRow) bool {
	for _, name := range []string{"previous_response_id", "conversation"} {
		if ref, ok := fields[name]; ok && string(ref) != "null" {
			return true
		}
	}
	var items []struct{ Type string }
	if json.Unmarshal(fields["input"], &items) == nil {
		for _, item := range items {
			if item.Type == "item_reference" {
				return true
			}
		}
	}
	return false
}

func (g *gateway) eligibleAlias(version, model string) bool {
	for _, row := range g.config.Catalogs[version] {
		if field(row, "slug") == model {
			return true
		}
	}
	return false
}

func (g *gateway) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if !equalToken(r.Header.Values("X-Route-Token"), g.config.GatewayToken) {
		reject(w, 401, "Local gateway credential rejected")
		return
	}
	if r.Method == "GET" && r.URL.Path == "/v1/models" {
		g.catalog(w, r)
		return
	}
	if r.Method == "POST" && (r.URL.Path == "/v1/images/generations" || r.URL.Path == "/v1/images/edits") {
		g.image(w, r)
		return
	}
	if r.Method != "POST" || (r.URL.Path != "/v1/responses" && r.URL.Path != "/v1/responses/compact") {
		reject(w, 404, "Unsupported gateway endpoint")
		return
	}
	if enc := r.Header.Get("Content-Encoding"); enc != "" && enc != "identity" {
		reject(w, 415, "Unsupported request encoding")
		return
	}
	raw, err := io.ReadAll(http.MaxBytesReader(w, r.Body, inputLimit))
	if err != nil {
		reject(w, 413, "Request body exceeds limit or could not be read")
		return
	}
	var fields modelRow
	if json.Unmarshal(raw, &fields) != nil {
		reject(w, 400, "Invalid Responses request")
		return
	}
	if hasServerReference(fields) {
		reject(w, 400, "Stateless HTTP requires replayed conversation input")
		return
	}
	version, _, _ := strings.Cut(r.Header.Get("Version"), "-")
	if _, ok := g.config.Catalogs[version]; !ok {
		// A fixture or client without a Version header can use a single staged version.
		if version != "" || len(g.config.Catalogs) != 1 {
			reject(w, 409, "Unsupported Codex version")
			return
		}
		for v := range g.config.Catalogs {
			version = v
		}
	}
	model := field(fields, "model")
	target := g.native
	isRoute := strings.HasPrefix(model, "route-")
	if isRoute {
		if !g.eligibleAlias(version, model) {
			reject(w, 400, "Unknown or revoked Route model")
			return
		}
		fields["model"], _ = json.Marshal(strings.TrimPrefix(model, "route-"))
		raw, err = json.Marshal(fields)
		if err != nil {
			reject(w, 400, "Invalid model request")
			return
		}
		target = g.route
	} else {
		if r.Header.Get("Authorization") == "" {
			reject(w, 403, "Native model unavailable for this account")
			return
		}
		key := identity(r, version)
		g.mu.RLock()
		entry := g.nativeModels[key]
		g.mu.RUnlock()
		// Codex may have cached the catalog before a relay restart or native token refresh.
		if time.Now().After(entry.expires) {
			if _, err := g.nativeCatalog(r, version); err != nil {
				reject(w, 502, err.Error())
				return
			}
			g.mu.RLock()
			entry = g.nativeModels[key]
			g.mu.RUnlock()
		}
		if !entry.slugs[model] {
			reject(w, 403, "Native model unavailable for this account")
			return
		}
	}
	if r.URL.Path == "/v1/responses" && !g.bindTurn(r, turnID(r, fields), model, version) {
		reject(w, 409, "Conflicting or unavailable turn binding")
		return
	}
	g.proxy(w, r, raw, target, isRoute)
}

func (g *gateway) proxy(w http.ResponseWriter, r *http.Request, raw []byte, target *url.URL, isRoute bool) {
	proxy := httputil.ReverseProxy{
		Rewrite: func(pr *httputil.ProxyRequest) {
			pr.Out.URL.Scheme = target.Scheme
			pr.Out.URL.Host = target.Host
			pr.Out.URL.Path = target.Path + strings.TrimPrefix(r.URL.Path, "/v1")
			pr.Out.URL.RawPath = ""
			pr.Out.URL.RawQuery = ""
			pr.Out.Host = target.Host
			pr.Out.Header = make(http.Header)
			pr.Out.Header.Set("Content-Type", "application/json")
			pr.Out.Header.Set("Accept", r.Header.Get("Accept"))
			if isRoute {
				pr.Out.Header.Set("Authorization", "Bearer "+g.config.RouteKey)
			} else {
				nativeHeaders(r.Header, pr.Out.Header)
			}
			pr.Out.Body = io.NopCloser(bytes.NewReader(raw))
			pr.Out.ContentLength = int64(len(raw))
			pr.Out.GetBody = nil
		},
		FlushInterval: -1,
		ErrorLog:      log.New(io.Discard, "", 0),
		ErrorHandler:  func(w http.ResponseWriter, _ *http.Request, _ error) { reject(w, 502, "Upstream connection failed") },
	}
	proxy.ServeHTTP(w, r)
}

func equalToken(values []string, token string) bool {
	return len(values) == 1 && subtle.ConstantTimeCompare([]byte(values[0]), []byte("Bearer "+token)) == 1
}

func run() error {
	var c config
	if err := json.NewDecoder(os.Stdin).Decode(&c); err != nil {
		return errors.New("invalid dispatcher configuration")
	}
	g, err := newGateway(c)
	if err != nil {
		return err
	}
	dir, err := os.Stat(filepath.Dir(c.Socket))
	if err != nil || !dir.IsDir() || (runtime.GOOS != "windows" && dir.Mode().Perm()&0077 != 0) {
		return errors.New("dispatcher socket requires a private directory")
	}
	addr, err := net.Listen("unix", c.Socket)
	if err != nil {
		return err
	}
	defer addr.Close()
	controlSocket, err := net.Listen("unix", c.Socket+".control")
	if err != nil {
		return err
	}
	defer controlSocket.Close()
	dispatch := &dispatcher{}
	dispatch.active.Store(g)
	controlServer := http.Server{Handler: http.HandlerFunc(dispatch.control), ReadHeaderTimeout: 10 * time.Second, ErrorLog: log.New(io.Discard, "", 0)}
	defer controlServer.Close()
	go controlServer.Serve(controlSocket)
	server := http.Server{Handler: dispatch, ReadHeaderTimeout: 10 * time.Second, ErrorLog: log.New(io.Discard, "", 0)}
	if c.Lease != "" {
		go func() {
			// Allow the parent to stage Caddy and atomically publish the new token.
			time.Sleep(10 * time.Second)
			for {
				value, err := os.ReadFile(c.Lease)
				if err != nil || !equalToken([]string{"Bearer " + string(value)}, c.GatewayToken) {
					server.Close()
					return
				}
				time.Sleep(time.Second)
			}
		}()
	}
	return server.Serve(addr)
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
