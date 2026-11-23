"""Paired first-complete-event benchmark. The local threshold is not a live SLA."""
import http.client
import json
import math
import platform
import subprocess
import time

from route.relay import CADDY, Relay
from tests.fixture import free_port, provider


def measure(port, token, payload, *, live=False, auth_header='Authorization'):
    conn = (http.client.HTTPSConnection('api.openai.com', timeout=90) if live
            else http.client.HTTPConnection('127.0.0.1', port, timeout=90))
    try:
        start = time.perf_counter_ns()
        conn.request('POST', '/v1/responses', payload, {auth_header: 'Bearer ' + token, 'Content-Type': 'application/json'})
        response = conn.getresponse()
        if response.status != 200:
            raise RuntimeError(f'HTTP {response.status}')
        data = []
        first = None
        finished = False
        for line in response:
            if line.startswith(b'data:'):
                data.append(line[5:].strip())
            elif not line.strip() and data:
                event = json.loads(b'\n'.join(data))
                if first is None:
                    first = (time.perf_counter_ns() - start) / 1e6
                data.clear()
                if event['type'] == 'response.completed':
                    finished = True
                    break
        if not finished:
            raise RuntimeError('Incomplete benchmark stream')
        return [round(first, 3), round((time.perf_counter_ns() - start) / 1e6, 3)]
    finally:
        conn.close()


def main():
    import argparse
    from getpass import getpass
    p = argparse.ArgumentParser()
    p.add_argument('--pairs', type=int, default=40)
    p.add_argument('--live', action='store_true', help='Send paid paired requests to OpenAI')
    p.add_argument('--combined-dispatcher', help='Benchmark the authenticated Caddy and Go path with local fixtures')
    args = p.parse_args()
    if args.combined_dispatcher and args.live:
        p.error('--combined-dispatcher uses only the deterministic local upstream')
    if args.pairs < 1:
        p.error('pairs must be positive')
    def stream(h, raw):
        h.start()
        h.event('response.created')
        h.event('response.completed')
    payload = json.dumps({'model': 'gpt-6.2-sol', 'input': 'Reply OK.', 'stream': True}).encode()
    key = getpass('OpenAI API key: ') if args.live else 'dummy'
    from contextlib import ExitStack
    from pathlib import Path
    import tempfile
    with provider(stream) as port, ExitStack() as stack:
        relay_header = 'Authorization'
        relay_payload = payload
        if args.combined_dispatcher:
            from route.relay import combined_configuration
            from tests.combined import ALIAS, service, listening
            work = Path(stack.enter_context(tempfile.TemporaryDirectory(dir='/tmp')))
            sock = work / 'dispatch.sock'
            relay_port, relay_token = free_port(), 'local-benchmark'
            origin = f'http://127.0.0.1:{port}'
            stack.enter_context(service([args.combined_dispatcher], dict(Socket=str(sock), GatewayToken=relay_token,
                RouteKey=key, NativeURL=origin, RouteURL=origin, Catalogs={'fixture': [{'slug': ALIAS}]}), sock.exists))
            stack.enter_context(service([CADDY, 'run', '--config', '-'], combined_configuration(relay_port, sock),
                                        lambda: listening(relay_port)))
            relay_header = 'X-Route-Token'
            relay_payload = json.dumps(dict(json.loads(payload), model=ALIAS)).encode()
        else:
            relay = Relay(free_port(), key, **({} if args.live else {'origin': f'127.0.0.1:{port}'}))
            stack.callback(relay.close)
            relay_port, relay_token = relay.port, relay.token
        pairs = []
        for i in range(args.pairs):
            pair = {}
            for label in (('direct', 'relay') if i % 2 == 0 else ('relay', 'direct')):
                pair[label] = (measure(port, key, payload, live=args.live) if label == 'direct'
                               else measure(relay_port, relay_token, relay_payload, auth_header=relay_header))
            pairs.append(pair)
    differences = sorted(p['relay'][0] - p['direct'][0] for p in pairs)
    p95 = round(differences[math.ceil(.95 * len(pairs)) - 1], 3)
    print(json.dumps({'os': platform.platform(), 'python': platform.python_version(), 'route': '0.1.0.dev0',
                      'caddy': subprocess.check_output([CADDY, 'version'], text=True).strip(),
                      'live': args.live, 'provider': 'route-combined' if args.combined_dispatcher else 'route', 'count': len(pairs), 'timings_ms_first_and_total': pairs,
                      'p95_added_ms': p95, 'passed': None if args.live else p95 <= 50}))
    return int(not args.live and p95 > 50)


if __name__ == '__main__':
    raise SystemExit(main())
