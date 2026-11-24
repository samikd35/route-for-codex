"""Terminal progress for the bootstrap and the installed onboarding command."""
from contextlib import contextmanager
import itertools
import os
import sys
import threading
import time


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
            mark = 'OK' if done else 'Stopped'
            print(f'\r{mark}  {label}  {int(time.monotonic() - start)}s', file=stream, flush=True)
