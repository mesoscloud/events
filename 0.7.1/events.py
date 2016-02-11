#!/usr/local/bin/python3

import json
import os
import re
import select
import time

import docker
import riemann

import riemann_client.client
import riemann_client.transport


def handle_log(client, container, line):
    if len(line) == 8:
        container.logs_stream = 'stdout' if line[0] == 1 else 'stderr'
        return

    events = riemann.handle_log(line, container._info, container.logs_stream)

    for event in events:
        client.event(**event)
        client.flush()


def handle_stat(client, container, line):
    data = json.loads(line.decode('utf-8'))

    events = riemann.handle_stat(data, container._info)

    for event in events:
        client.event(**event)
        client.flush()


def summarise(line, width=60):
    """Summarise

        >>> summarise('hi')
        'hi'

        >>> summarise('hi ' * 100)
        'hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi hi ...'

    """
    return line[:width] + '...' if len(line) > width else line[:width]


def main():
    riemann_host = os.getenv('RIEMANN_HOST', 'localhost')
    riemann_port = int(os.getenv('RIEMANN_PORT', '5555'))

    containers1 = []

    epoll = select.epoll()

    start = 0

    buffy = {}

    try:
        with open('/srv/events/since') as f:
            docker.Container.since = int(f.read().rstrip())
        print('since', docker.Container.since)
    except FileNotFoundError:
        pass
    except ValueError:
        pass

    with riemann_client.client.QueuedClient(riemann_client.transport.TCPTransport(riemann_host, riemann_port)) as client:

        while 1:

            # tight loops are bad mmkay
            time.sleep(0.05)

            if time.time() - start >= 1.0:
                start = time.time()

                containers2 = docker.containers()

                a = [x for x in containers1 if x not in containers2]
                b = [x for x in containers2 if x not in containers1]

                for container in a:
                    print('remove', container)

                    container.logs_stop(epoll)

                    if container.logs_fd is not None:
                        if buffy.get(container.logs_fd):
                            print(container, 'logs', 'remaining', summarise(repr(buffy[container.logs_fd])))
                        try:
                            del buffy[container.logs_fd]
                        except KeyError:
                            pass

                    container.stats_stop(epoll)

                    if container.stats_fd is not None:
                        if buffy.get(container.stats_fd):
                            print(container, 'stats', 'remaining', summarise(repr(buffy[container.stats_fd])))
                        try:
                            del buffy[container.stats_fd]
                        except KeyError:
                            pass

                    containers1.remove(container)

                for container in b:

                    try:
                        info = container.inspect()
                    except docker.HTTPError:
                        continue

                    container._info = info

                    if info['Config']['Tty']:
                        continue

                    print('append', container)

                    try:
                        container.logs_start(epoll)
                    except docker.HTTPError as exc:
                        print(container, exc)
                        continue

                    try:
                        container.stats_start(epoll)
                    except docker.HTTPError as exc:
                        print(container, exc)
                        continue

                    containers1.append(container)

                for container in containers1:
                    container.logs_check(epoll)
                    container.stats_check(epoll)

                #
                docker.Container.since = int(time.time()) - 10
                with open('/srv/events/since', 'w') as f:
                    print(docker.Container.since, file=f)
                #print('since', docker.Container.since)

            #
            for fd, event in epoll.poll(0):

                container = None
                try:
                    container = [x for x in containers1 if x.logs_fd and x.logs_fd == fd][0]
                except IndexError:
                    pass
                try:
                    container = [x for x in containers1 if x.stats_fd and x.stats_fd == fd][0]
                except IndexError:
                    pass

                assert container is not None

                data = os.read(fd, 8192)

                data = buffy.get(fd, b'') + data

                while 1:
                    data, line = docker.parse(data)
                    if not line:
                        break

                    if container is not None:
                        if fd == container.logs_fd:
                            handle_log(client, container, line)
                        if fd == container.stats_fd:
                            handle_stat(client, container, line)

                    if not data:
                        break

                buffy[fd] = data


if __name__ == '__main__':
    main()
