#!/usr/bin/python -u
#
# Copyright (c) 2015 Peter Ericson <pdericson@gmail.com>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import concurrent.futures
import datetime
import http.client
import json
import os
import re
import select
import socket
import sys
import time
import traceback

from docker import *
from riemann import handle_event, handle_log, handle_stat, write_log
#from debug import handle_event, handle_log, handle_stat, write_log


executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)


def docker_containers():
    return get('/containers/json')


def docker_inspect(id_):
    return get('/containers/%s/json' % id_)


def docker_events():
    return executor.submit(get, '/events', async=True)


def docker_logs(id_, since=None):
    if since is not None:
        since = '&since=%s' % int(since)
    else:
        since = ''
    return executor.submit(get, '/containers/%s/logs?follow=1&stdout=1&stderr=1%s&timestamps=1' % (id_, since), async=True)


def docker_stats(id_):
    return executor.submit(get, '/containers/%s/stats' % id_, async=True)


def is_running_or_pending(item):
    item = item['p']

    if not item.done():
        return True

    try:
        result = item.result()
    except HTTPError as exc:
        if exc.status != 404:
            raise
        return False

    if result.fp is None:
        return False

    return True


def is_running(item):
    item = item['p']

    if not item.done():
        return False

    try:
        result = item.result()
    except HTTPError as exc:
        if exc.status != 404:
            raise
        return False

    if result.fp is None:
        return False

    return True


def since(info):
    """Since

        >>> since({'State': {'StartedAt': '2015-12-02T23:54:02.099502934Z'}})
        1449100442

        >>> since({'State': {'StartedAt': '2015-12-02T23:54:02Z'}})
        1449100442

    """
    startedat = info['State']['StartedAt'][:len('2015-12-02T23:54:02')]
    return int((datetime.datetime.strptime(startedat, '%Y-%m-%dT%H:%M:%S') - datetime.datetime(1970,1,1)).total_seconds())


def main():

    logs = []

    stats = []

    for container in docker_containers():

        try:
            info = docker_inspect(container['Id'])
        except HTTPError as exc:
            if exc.status != 404:
                raise
            continue

        if info['Config']['Tty']:
            continue

        print("%(Id).12s: logs" % info)
        logs.append({
            'p': docker_logs(container['Id'], since=time.time()),
            'info': info,
        })
        print("%(Id).12s: stats" % info)
        stats.append({
            'p': docker_stats(container['Id']),
            'info': info,
            'id': container['Id'],
        })

    events = docker_events()

    write_count = 0
    write_start = time.time()

    log_queue = []

    partial = {}

    while True:

        logs = list(filter(is_running_or_pending, logs))

        stats = list(filter(is_running_or_pending, stats))

        rlist = ([events.result()] if events.done() else []) + [x['p'].result() for x in filter(is_running, logs)] + [x['p'].result() for x in filter(is_running, stats)]

        if not rlist:
            time.sleep(1)
            continue

        try:
            rs, _, _ = select.select(rlist, [], [], 1)
        except AttributeError as exc:
            # AttributeError: 'NoneType' object has no attribute 'fileno'
            time.sleep(0.05)
            continue
        except ValueError as exc:
            # ValueError: filedescriptor out of range in select()
            time.sleep(0.05)
            continue

        for r in rs:

            stream = None

            for part in os.read(r.fileno(), 8192).split(b'\r\n'):

                part = partial.pop(r, b'') + part

                if part == b'':
                    continue

                if part[:7] == b'\x01\x00\x00\x00\x00\x00\x00':
                    stream = 'stdout'
                if part[:7] == b'\x02\x00\x00\x00\x00\x00\x00':
                    stream = 'stderr'

                if part.startswith(b'{'):
                    try:
                        json.loads(part.decode('utf-8'))
                    except Exception as exc:
                        partial[r] = part
                        continue
                elif re.match(rb'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', part):
                    pass
                else:
                    continue

                line = part

                if events.done() and r is events.result():
                    data = json.loads(line.decode('utf-8'))

                    try:
                        log_queue += handle_event(data)
                    except Exception as exc:
                        print("Unable to handle event: %r" % data, file=sys.stderr)
                        traceback.print_exc()

                    if data['status'] == 'start':

                        try:
                            info = docker_inspect(data['id'])
                        except HTTPError as exc:
                            if exc.status != 404:
                                raise
                            continue

                        if info['Config']['Tty']:
                            continue

                        print("%(Id).12s: logs" % info)
                        logs.append({
                            'p': docker_logs(data['id'], since(info)),
                            'info': info,
                        })
                        if not [x for x in stats if x['id'] == info['Id']]:
                            print("%(Id).12s: stats" % info)
                            stats.append({
                                'p': docker_stats(data['id']),
                                'info': info,
                                'id': info['Id'],
                            })

                elif r in [x['p'].result() for x in filter(is_running, logs)]:

                    try:
                        info = [l['info'] for l in filter(is_running, logs) if r == l['p'].result()][0]
                    except IndexError:
                        continue

                    try:
                        log_queue += handle_log(line, info, stream)
                    except Exception as exc:
                        print("Unable to handle log: %r" % line, file=sys.stderr)
                        traceback.print_exc()

                elif r in [x['p'].result() for x in filter(is_running, stats)]:

                    try:
                        info = [s['info'] for s in filter(is_running, stats) if r == s['p'].result()][0]
                    except IndexError:
                        continue

                    data = json.loads(line.decode('utf-8'))

                    try:
                        log_queue += handle_stat(data, info)
                    except Exception as exc:
                        print("Unable to handle stat: %r" % data, file=sys.stderr)
                        traceback.print_exc()


        if log_queue:

            write_count += len(log_queue)
            try:
                write_log(log_queue)
            except Exception as exc:
                traceback.print_exc()

            try:
                while True:
                    log_queue.pop()
            except IndexError:
                pass

        if time.time() - write_start >= 10:
            print("events:", write_count)
            write_start = time.time()

        time.sleep(1)


if __name__ == '__main__':
    main()
