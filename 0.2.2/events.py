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

import collections
import concurrent.futures
import datetime
import glob
import http.client
import json
import os
import re
import select
import socket
import sys
import threading
import time
import traceback


keep_seconds = int(os.getenv('KEEP_SECONDS', 1 * 60 * 60))

log_path = '/srv/events/containers.log'
log_time = 1 * 60
log_size = 1 * 1024 * 1024

executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

queue = collections.deque()


class HTTPConnection(http.client.HTTPConnection):

    def __init__(self):
        http.client.HTTPConnection.__init__(self, 'localhost')

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect('/var/run/docker.sock')
        self.sock = sock


class HTTPError(Exception):

    def __init__(self, status, reason):
        self.status = status
        self.reason = reason


def _get_json(path):
    conn = HTTPConnection()
    conn.request('GET', path)
    resp = conn.getresponse()
    if resp.status != 200:
        raise HTTPError(resp.status, resp.reason)
    return json.loads(resp.read().decode('utf-8'))


def _get_file(path):
    conn = HTTPConnection()
    conn.request('GET', path)
    resp = conn.getresponse()
    if resp.status != 200:
        raise HTTPError(resp.status, resp.reason)
    return resp


def docker_containers():
    return _get_json('/containers/json')


def docker_inspect(id_):
    return _get_json('/containers/%s/json' % id_)


def docker_events():
    return executor.submit(_get_file, '/events')


def docker_logs(id_, since=None):
    if since is not None:
        since = '&since=%s' % int(since)
    else:
        since = ''
    return executor.submit(_get_file, '/containers/%s/logs?follow=1&stdout=1&stderr=1%s&timestamps=1' % (id_, since))


def docker_stats(id_):
    return executor.submit(_get_file, '/containers/%s/stats' % id_)


def write_log(data):
    queue.append(data)


def handle_logs():

    with open(log_path, 'a') as f:
        while True:
            try:
                data = queue.popleft()
            except IndexError:
                break
            print(json.dumps(data), file=f)

    try:
        st = os.stat(log_path)

        a = datetime.datetime.utcnow()
        b = datetime.datetime.utcfromtimestamp(st.st_ctime)
        c = st.st_size
        d = datetime.datetime.utcfromtimestamp(st.st_mtime)

        if a - b > datetime.timedelta(seconds=log_time) or c > log_size:
            dst = log_path + '-' + d.strftime('%Y%m%d%H%M%S')
            if not os.path.exists(dst):
                print('mv', log_path, dst, file=sys.stderr)
                os.rename(log_path, dst)
    except FileNotFoundError:
        pass

    for path in sorted(glob.glob(log_path + '-*')):

        a = datetime.datetime.utcnow()
        b = datetime.datetime.strptime(path.split('-')[-1], '%Y%m%d%H%M%S')
        c = datetime.timedelta(seconds=keep_seconds)

        if a - b > c:
            print('rm', path, file=sys.stderr)
            os.remove(path)


def handle_event(data):

    data2 = {
        '@timestamp': datetime.datetime.utcfromtimestamp(data['time']).strftime('%Y-%m-%dT%H:%M:%SZ'),
    }

    for k, v in data.items():
        if k == 'time':
            continue
        data2['event_' + k] = v

    return data2


def handle_log(line, info):
    """Handle a line of log output

        >>> info = {'Id': '', 'Image': '', 'Name': '', 'Config': {'Image': ''}}

    Normal

        >>> data = handle_log(b"\\x01" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data['log']
        'HERE'

        >>> data = handle_log(b"\\x02" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data['log']
        'HERE'

    Not so normal

    Double magic

        >>> data = handle_log(b"\\x01" + (b"\\x00" * 7) + b"\\x01" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data['log']
        'HERE'

    No magic

        >>> data = handle_log(b'2015-08-31T14:36:35.179583676Z HERE', info)
        >>> data['log']
        'HERE'

    Bad magic

        >>> data = handle_log(b'\\xb02015-08-31T14:41:43.702708748Z HERE', info)
        >>> data['log']
        'HERE'

    """

    try:
        a = {1: 'stdout', 2: 'stderr'}[line[0]]
    except KeyError as exc:
        print("Unable to detect stream: %r" % line, file=sys.stderr)
        a = 'stdout'  # We don't know

    m = re.search(rb'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z ', line)
    if m is None:
        raise Exception("missing timestamp")

    line = line[m.start():]

    b = line[:30]
    c = line[31:]

    data = {
        '@timestamp': b.decode('utf-8'),

        'log': c.decode('utf-8'),
        'stream': a,

        # info
        'container': info['Name'],
        'container_id': info['Id'],
        'image': info['Config']['Image'],
        'image_id': info['Image'],
    }

    return data


def handle_stat(data, info):

    data2 = {
        '@timestamp': data['read'],

        # info
        'container': info['Name'],
        'container_id': info['Id'],
        'image': info['Config']['Image'],
        'image_id': info['Image'],
    }

    # blkio_stats
    for k, v in data['blkio_stats'].items():
        for x in v:
            data2['blkio_' + k + '_' + x['op'].lower()] = x['value']

    # cpu_stats
    for k in [
            'total_usage',
            'usage_in_kernelmode',
            'usage_in_usermode',
            ]:
        data2['cpu_' + k] = data['cpu_stats']['cpu_usage'][k]

    for i, x in enumerate(data['cpu_stats']['cpu_usage']['percpu_usage']):
        data2['cpu_percpu_usage' + str(i)] = x

    # memory_stats
    data2['memory_limit'] = data['memory_stats']['limit']
    data2['memory_usage'] = data['memory_stats']['usage']

    # https://www.kernel.org/doc/Documentation/cgroups/memory.txt
    for k in [
            'active_anon',
            'active_file',
            'cache',
            #'hierarchical_memory_limit',
            #'hierarchical_memsw_limit',
            'inactive_anon',
            'inactive_file',
            'mapped_file',
            'pgfault',
            'pgmajfault',
            'pgpgin',
            'pgpgout',
            'rss',
            'rss_huge',
            'swap',
            'unevictable',
            'writeback',
    ]:
        try:
            data2['memory_' + k] = data['memory_stats']['stats'].get('total_' + k, data['memory_stats']['stats'][k])
        except KeyError:
            # swap
            pass

    # network
    for k, v in data['network'].items():
        data2['network_' + k] = v

    # precpu_stats
    #data2['precpu_stats'] = data['precpu_stats']

    return data2


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

        logs.append({
            'p': docker_logs(container['Id'], since=time.time()),
            'info': info,
        })
        stats.append({
            'p': docker_stats(container['Id']),
            'info': info,
        })

    events = docker_events()

    timer = time.time()
    while True:

        if time.time() - timer > 10 or len(queue) > 1000:
            handle_logs()
            timer = time.time()

        time.sleep(0.05)

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
            continue

        for r in rs:
            line = r.readline()
            if not line:
                continue

            if events.done() and r is events.result():
                data = json.loads(line.decode('utf-8'))

                try:
                    write_log(handle_event(data))
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

                    logs.append({
                        'p': docker_logs(data['id']),
                        'info': info,
                    })
                    stats.append({
                        'p': docker_stats(data['id']),
                        'info': info,
                    })

            elif r in [x['p'].result() for x in filter(is_running, logs)]:

                try:
                    info = [l['info'] for l in filter(is_running, logs) if r == l['p'].result()][0]
                except IndexError:
                    continue

                try:
                    write_log(handle_log(line, info))
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
                    write_log(handle_stat(data, info))
                except Exception as exc:
                    print("Unable to handle stat: %r" % data, file=sys.stderr)
                    traceback.print_exc()


if __name__ == '__main__':
    main()
