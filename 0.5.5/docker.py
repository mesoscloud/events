"""docker"""

import http.client
import json
import socket

__all__ = ['HTTPConnection', 'HTTPError', 'get']


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
