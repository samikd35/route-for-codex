// Windows Python lacks AF_UNIX on some versions. Keep the Caddy admin API on
// the same private filesystem socket, not an unauthenticated loopback port.
package main

import (
	"context"
	"net"
	"net/http"
	"os"
	"time"
)

func main() {
	if len(os.Args) != 3 { os.Exit(2) }
	sock, action := os.Args[1], os.Args[2]
	dial := func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{}).DialContext(ctx, "unix", sock)
	}
	if action == "ping" {
		conn, err := net.DialTimeout("unix", sock, time.Second)
		if err != nil { os.Exit(1) }
		conn.Close()
		return
	}
	method := "POST"
	if action == "/config/apps/http/servers/route/routes/0/match/0/path" { method = "PATCH" } else if action != "/load" && action != "/stop" { os.Exit(2) }
	client := http.Client{Transport: &http.Transport{DialContext: dial}, Timeout: 10 * time.Second}
	req, err := http.NewRequest(method, "http://localhost" + action, os.Stdin)
	if err != nil { os.Exit(1) }
	req.Header.Set("Content-Type", "application/json")
	res, err := client.Do(req)
	if err != nil { os.Exit(1) }
	defer res.Body.Close()
	if res.StatusCode != 200 { os.Exit(1) }
}
