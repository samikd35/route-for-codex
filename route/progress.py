"""Terminal progress for the bootstrap and the installed onboarding command."""
from contextlib import contextmanager
import itertools
import os
import sys
import threading
import time


def accent(text, stream):
    if (stream.isatty() and os.environ.get('TERM') != 'dumb' and 'NO_COLOR' not in os.environ
            and (os.name != 'nt' or os.environ.get('WT_SESSION') or os.environ.get('TERM'))):
        return f'\033[1;36m{text}\033[0m'
    return text


@contextmanager
def stage(label):
    stream = sys.stderr
    animated = stream.isatty() and os.environ.get('TERM') != 'dumb' and not os.environ.get('ROUTE_VERBOSE')
    start = time.monotonic()
    stop = threading.Event()

    def animate():
        for frame in itertools.cycle('|/-\\'):
            stream.write(f'\r{frame} {label}  {int(time.monotonic() - start)}s')
            stream.flush()
            if stop.wait(.15):
                break

    worker = None
    if animated:
        worker = threading.Thread(target=animate, daemon=True)
        worker.start()
    else:
        print(label, file=stream, flush=True)
    done = False
    try:
        yield
        done = True
    finally:
        if worker:
            stop.set()
            worker.join()
            mark = 'Stopped'
            if done:
                symbol = '✓' if (stream.encoding or '').lower().startswith('utf') else 'OK'
                mark = accent(symbol, stream)
            print(f'\r{mark}  {label}  {int(time.monotonic() - start)}s', file=stream, flush=True)
