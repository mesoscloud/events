#!/usr/local/bin/python3

import os
import signal
import subprocess
import sys
import time


def wait(p):
    for _ in range(10):
        if p.poll() is not None:
            break
        time.sleep(1)


def main():

    if not os.path.exists('/srv/events/since'):
        with open('/srv/events/since', 'w') as f:
            print('0', file=f)

    while 1:

        a = time.time()
        b = os.stat('/srv/events/since').st_mtime

        cmd = [sys.executable, './events.py']
        print("watchdog: exec", ' '.join(cmd))
        p = subprocess.Popen(cmd)

        while p.poll() is None:

            c = os.stat('/srv/events/since').st_mtime
            if c > b:
                a = c
            d = time.time() - a

            print("watchdog: %.0fs" % d)

            if d > 30:
                print("watchdog: int")
                p.send_signal(signal.SIGINT)
                wait(p)

                print("watchdog: term")
                p.send_signal(signal.SIGTERM)
                wait(p)

                print("watchdog: kill")
                p.send_signal(signal.SIGKILL)
                wait(p)

                break

            wait(p)

        print("watchdog: exit", p.returncode)

        time.sleep(10)


if __name__ == '__main__':
    main()
