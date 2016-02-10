import concurrent.futures
import datetime
import http.client
import json
import pickle
import re
import select
import socket

__all__ = []


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


def get(path, async=False):
    conn = HTTPConnection()
    try:
        conn.request('GET', path)
        resp = conn.getresponse()

        if resp.status != 200:
            raise HTTPError(resp.status, resp.reason)
    except Exception:
        conn.close()
        raise

    try:
        if async:
            return resp
        elif resp.headers.get('Content-Type') == 'application/json':
            return json.loads(resp.read().decode('utf-8'))
        else:
            return resp.read()
    finally:
        if not async:
            conn.close()


def containers():
    return [Container(c['Id'], c['Created']) for c in get('/containers/json')]


class Container(object):

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    since = 0

    def __init__(self, id_, created):
        self.id_ = id_
        self.created = created

        self.logs = None
        self.logs_fd = None
        self.logs_stream = 'stdout'

        self.stats = None
        self.stats_fd = None

        self._info = None

    def __repr__(self):
        return "<Container %s created=%r>" % (self.id_, self.created)

    def __str__(self):
        return "%.12s" % self.id_

    def __eq__(self, other):
        if self.id_ == other.id_ and self.created == other.created:
            return True

    def inspect(self):
        return get('/containers/%s/json' % self.id_)

    def logs_start(self, epoll):
        try:
            info = self.inspect()
        except HTTPError as exc:
            raise

        url = '/containers/%s/logs?follow=1&stdout=1&stderr=1&since=%s&timestamps=1' % (self.id_, Container.since)

        print(self, url)

        self.logs = Container.executor.submit(get, url, async=True)

    def logs_stop(self, epoll):

        # Let's attempt to cancel the future just in case
        self.logs.cancel()

        try:
            logs = self.logs.result(timeout=0)
        except (concurrent.futures.CancelledError,
                concurrent.futures.TimeoutError,
                HTTPError) as exc:
            print(self, 'logs', exc)
            return

        try:
            fd = logs.fileno()
            epoll.unregister(fd)
            print(self, 'logs', "unregistered (fd=%s)." % fd)
        except FileNotFoundError:
            pass

        logs.close()

    def logs_check(self, epoll):
        if self.logs_fd is not None:
            return

        try:
            logs = self.logs.result(timeout=0)
        except (concurrent.futures.TimeoutError,
                HTTPError) as exc:
            print(self, 'logs', exc)
            return

        print(self, 'logs', logs)

        self.logs_fd = logs.fileno()

        print(self, 'logs', self.logs_fd)

        try:
            epoll.register(self.logs_fd, select.EPOLLIN)
            print(self, 'logs', "registered (fd=%s)." % self.logs_fd)
        except FileExistsError:
            return

    def stats_start(self, epoll):
        try:
            info = self.inspect()
        except HTTPError as exc:
            raise

        url = '/containers/%s/stats' % self.id_

        print(self, url)

        self.stats = Container.executor.submit(get, url, async=True)

    def stats_stop(self, epoll):

        # Let's attempt to cancel the future just in case
        self.stats.cancel()

        try:
            stats = self.stats.result(timeout=0)
        except (concurrent.futures.CancelledError,
                concurrent.futures.TimeoutError,
                HTTPError) as exc:
            print(self, 'stats', exc)
            return

        try:
            fd = stats.fileno()
            epoll.unregister(fd)
            print(self, 'stats', "unregistered (fd=%s)." % fd)
        except FileNotFoundError:
            pass

        stats.close()

    def stats_check(self, epoll):
        if self.stats_fd is not None:
            return

        try:
            stats = self.stats.result(timeout=0)
        except (concurrent.futures.TimeoutError,
                HTTPError) as exc:
            print(self, 'stats', exc)
            return

        print(self, 'stats', stats)

        self.stats_fd = stats.fileno()

        print(self, 'stats', self.stats_fd)

        try:
            epoll.register(self.stats_fd, select.EPOLLIN)
            print(self, 'stats', "registered (fd=%s)." % self.stats_fd)
        except FileExistsError:
            return


def parse(data):
    """Parse stream

        >>> parse(b'80\\r\\n{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7","time":1445856406}\\n\\r\\n')
        (b'', b'{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7","time":1445856406}\\n')

        >>> parse(b'80\\r\\n{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7","time":1445856406}\\n')
        (b'80\\r\\n{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7","time":1445856406}\\n', b'')

        >>> parse(b'80\\r\\n{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7"')
        (b'80\\r\\n{"status":"create","id":"46e344569d70e9cf849a217701d5ef2e866dff122c1d5f1641b490e680c15c5d","from":"centos:7"', b'')

    """
    if not re.match(rb'[0-9a-f]+\r\n.*\r\n', data, re.I|re.S):
        return data, b''

    i = data.find(b'\r\n')

    x = data[:i]
    y = int(x, 16)

    data = data[i + 2:]
    if len(data) < y + 2:
        return data, b''

    line = data[:y]
    data = data[y + 2:]

    return data, line
