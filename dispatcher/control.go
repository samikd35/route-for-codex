package main

import (
	"context"
	"encoding/json"
	"maps"
	"net/http"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

// Data requests take one immutable snapshot. Only the owner of the separate private
// control socket can publish a replacement key and its eligible catalogs.
type dispatcher struct {
	active atomic.Pointer[gateway]
	update sync.Mutex
}

func (d *dispatcher) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	g := d.active.Load()
	version := r.Header.Get("Version")
	catalog := r.Method == "GET" && r.URL.Path == "/v1/models"
	if catalog {
		version = r.URL.Query().Get("client_version")
	}
	version, _, _ = strings.Cut(version, "-")
	if _, known := g.config.Catalogs[version]; !known && len(g.config.CatalogCommand) > 0 &&
		(catalog || r.Method == "POST") && validVersion.MatchString(version) &&
		equalToken(r.Header.Values("X-Route-Token"), g.config.GatewayToken) {
		g = d.refresh(r.Context(), version)
	}
	g.ServeHTTP(w, r)
}

var validVersion = regexp.MustCompile(`^[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}$`)

// Discover metadata only from installed Codex programs. The helper receives a
// version, never the API key, prompt, native credentials, or request headers.
func (d *dispatcher) refresh(ctx context.Context, version string) *gateway {
	d.update.Lock()
	defer d.update.Unlock()
	current := d.active.Load()
	cfg := current.config
	if _, known := cfg.Catalogs[version]; known {
		return current
	}
	ctx, cancel := context.WithTimeout(ctx, 40*time.Second)
	defer cancel()
	args := append([]string{}, cfg.CatalogCommand[1:]...)
	command := exec.CommandContext(ctx, cfg.CatalogCommand[0], append(args, "--client-version", version)...)
	data, err := command.Output()
	var rows []modelRow
	if err != nil || len(data) > catalogLimit || json.Unmarshal(data, &rows) != nil || rows == nil {
		return current
	}
	cfg.Catalogs = maps.Clone(cfg.Catalogs)
	cfg.Catalogs[version] = rows
	next, err := newGateway(cfg)
	if err != nil {
		return current
	}
	next.routingState = current.routingState
	d.active.Store(next)
	return next
}

func (d *dispatcher) control(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" || r.URL.Path != "/replace" {
		reject(w, 404, "Unsupported control operation")
		return
	}
	var update struct {
		RouteKey string
		Catalogs map[string][]modelRow
	}
	body := http.MaxBytesReader(w, r.Body, catalogLimit)
	dec := json.NewDecoder(body)
	dec.DisallowUnknownFields()
	if dec.Decode(&update) != nil || update.RouteKey == "" || len(update.Catalogs) == 0 {
		reject(w, 400, "Invalid replacement credential or catalogs")
		return
	}
	d.update.Lock()
	defer d.update.Unlock()
	current := d.active.Load()
	cfg := current.config
	cfg.RouteKey = update.RouteKey
	cfg.Catalogs = update.Catalogs
	next, err := newGateway(cfg)
	if err != nil {
		reject(w, 400, "Invalid replacement configuration")
		return
	}
	next.routingState = current.routingState
	d.active.Store(next)
	w.WriteHeader(204)
}
