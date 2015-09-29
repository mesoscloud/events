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

import copy
import datetime
import re
import shlex
import sys

import riemann_client.client
import riemann_client.transport


def handle_event(data):
    """Handle event

    create, etc

        >>> data = {'time': 0, 'id': 'abc', 'status': 'create', 'from': 'centos:7'}
        >>> events = handle_event(data)
        >>> len(events)
        1
        >>> event = events[0]

        >>> riemann_client.client.Client.create_event(copy.deepcopy(event))  # doctest: +ELLIPSIS
        <google.protobuf...>

        >>> event['time']
        0
        >>> event['state']
        'ok'
        >>> event['service']
        'docker'
        >>> event['tags']
        []
        >>> event['ttl']
        60
        >>> event['attributes']['event_status']
        'create'
        >>> event['attributes']['event_id']
        'abc'
        >>> event['attributes']['event_from']
        'centos:7'

    exec_start: ...

        >>> data = {'time': 0, 'id': 'abc', 'status': 'exec_start: <command>', 'from': 'centos:7'}
        >>> events = handle_event(data)
        >>> len(events)
        1
        >>> event = events[0]

        >>> riemann_client.client.Client.create_event(copy.deepcopy(event))  # doctest: +ELLIPSIS
        <google.protobuf...>

        >>> event['time']
        0
        >>> event['state']
        'ok'
        >>> event['service']
        'docker'
        >>> event['tags']
        []
        >>> event['ttl']
        60
        >>> event['attributes']['event_status']
        'exec_start: <command>'
        >>> event['attributes']['event_id']
        'abc'
        >>> event['attributes']['event_from']
        'centos:7'

    tag, etc

        >>> data = {'time': 0, 'id': 'abc', 'status': 'tag'}
        >>> events = handle_event(data)
        >>> len(events)
        1
        >>> event = events[0]
        >>> riemann_client.client.Client.create_event(copy.deepcopy(event))  # doctest: +ELLIPSIS
        <google.protobuf...>

        >>> event['time']
        0
        >>> event['state']
        'ok'
        >>> event['service']
        'docker'
        >>> event['tags']
        []
        >>> event['ttl']
        60
        >>> event['attributes']['event_status']
        'tag'
        >>> event['attributes']['event_id']
        'abc'
        >>> event['attributes']['event_from']
        ''

    """
    event = {
        'time': data['time'],
        'state': 'ok',
        'service': 'docker',
        'tags': [],
        'ttl': 60,
        'attributes': {
            'event_status': data['status'],
            'event_id': data['id'],
            'event_from': data.get('from', ''),
        },
    }
    return [event]


def handle_log(line, info):
    """Handle a line of log output

        >>> info = {'Id': '', 'Image': '', 'Name': 'foo', 'Config': {'Image': '', 'Cmd': [], 'Entrypoint': ''}}

    Normal

        >>> data = handle_log(b"\\x01" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data[0]['attributes']['log']
        'HERE'

        >>> data = handle_log(b"\\x02" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data[0]['attributes']['log']
        'HERE'

    Not so normal

    Double magic

        >>> data = handle_log(b"\\x01" + (b"\\x00" * 7) + b"\\x01" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE", info)
        >>> data[0]['attributes']['log']
        'HERE'

    No magic

        >>> data = handle_log(b'2015-08-31T14:36:35.179583676Z HERE', info)
        >>> data[0]['attributes']['log']
        'HERE'

    Bad magic

        >>> data = handle_log(b'\\xb02015-08-31T14:41:43.702708748Z HERE', info)
        >>> data[0]['attributes']['log']
        'HERE'

    XXX

        >>> line = b"\\x01" + (b"\\x00" * 7) + b"2015-08-31T14:41:43.702708748Z HERE"
        >>> info = {'Id': '', 'Image': '', 'Name': 'foo', 'Config': {'Image': '', 'Cmd': [], 'Entrypoint': ''}}

        >>> events = handle_log(line, info)

        >>> len(events)
        1
        >>> event = events[0]
        >>> riemann_client.client.Client.create_event(copy.deepcopy(event))  # doctest: +ELLIPSIS
        <google.protobuf...>

        >>> event['time']
        1441032103
        >>> event['state']
        'ok'
        >>> event['service']
        'container foo stdout'
        >>> event['tags']
        []
        >>> event['ttl']
        60

        >>> event['attributes']['container']
        'foo'
        >>> event['attributes']['container_id']
        ''
        >>> event['attributes']['image']
        ''
        >>> event['attributes']['image_id']
        ''
        >>> event['attributes']['log']
        'HERE'
        >>> event['attributes']['stream']
        'stdout'

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

    event = {
        'time': int((datetime.datetime.strptime(b.decode('utf-8').split('.')[0], '%Y-%m-%dT%H:%M:%S') - datetime.datetime(1970,1,1)).total_seconds()),
        'state': 'ok',
        'service': 'container %s %s' % (info['Name'].lstrip('/'), a),
        'tags': [],
        'ttl': 60,
        'attributes': {
            'container': info['Name'].lstrip('/'),
            'container_id': info['Id'],
            'image': info['Config']['Image'],
            'image_id': info['Image'],
            'container_cmd': ' '.join([shlex.quote(x) for x in (info['Config']['Cmd'] if info['Config']['Cmd'] is not None else [])]),

            'log': c.decode('utf-8'),
            'stream': a,
        },
    }
    return [event]


def handle_stat(data, info):
    """Handle stat

        >>> blkio_stats = {}
        >>> cpu_stats = {'cpu_usage': {'total_usage': 0, 'usage_in_kernelmode': 0, 'usage_in_usermode': 0, 'percpu_usage': []}}
        >>> memory_stats = {'limit': 0, 'usage': 0}
        >>> network = {}
        >>> data = {'read': '2015-09-23T04:13:56.297129480Z', 'blkio_stats': blkio_stats, 'cpu_stats': cpu_stats, 'memory_stats': memory_stats, 'network': network}
        >>> info = {'Name': 'foo', 'Id': '123', 'Config': {'Image': 'centos:7', 'Cmd': ['true'], 'Entrypoint': ''}, 'Image': 'abc'}
        >>> events = handle_stat(data, info)

        >>> len(events)
        5
        >>> event = events[0]
        >>> riemann_client.client.Client.create_event(copy.deepcopy(event))  # doctest: +ELLIPSIS
        <google.protobuf...>

        >>> event['time']
        1442981636
        >>> event['state']
        'ok'
        >>> event['service']
        'container foo cpu total usage'
        >>> event['tags']
        []
        >>> event['ttl']
        60
        >>> event['attributes']['container']
        'foo'
        >>> event['attributes']['container_id']
        '123'
        >>> event['attributes']['image']
        'centos:7'
        >>> event['attributes']['image_id']
        'abc'

    """

    events = []

    time_ = int((datetime.datetime.strptime(data['read'].split('.')[0], '%Y-%m-%dT%H:%M:%S') - datetime.datetime(1970,1,1)).total_seconds())

    attributes = {
        'container': info['Name'].lstrip('/'),
        'container_id': info['Id'],
        'image': info['Config']['Image'],
        'image_id': info['Image'],
        'container_cmd': ' '.join([shlex.quote(x) for x in (info['Config']['Cmd'] if info['Config']['Cmd'] is not None else [])]),
    }

    # blkio_stats
    for k, v in data['blkio_stats'].items():
        for x in v:
            event = {
                'time': time_,
                'state': 'ok',
                'service': 'container %s blkio %s %s' % (info['Name'].lstrip('/'), k, x['op'].lower()),
                'tags': [],
                'ttl': 60,
                'attributes': attributes,
                'metric_sint64': x['value'],
            }
            events.append(event)

    # cpu_stats
    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s cpu total usage' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': data['cpu_stats']['cpu_usage']['total_usage'],
    }
    events.append(event)

    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s cpu usage in kernelmode' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': data['cpu_stats']['cpu_usage']['usage_in_kernelmode'],
    }
    events.append(event)

    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s cpu usage in usermode' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': data['cpu_stats']['cpu_usage']['usage_in_usermode'],
    }
    events.append(event)

    for i, x in enumerate(data['cpu_stats']['cpu_usage']['percpu_usage']):
        event = {
            'time': time_,
            'state': 'ok',
            'service': 'container %s cpu usage in cpu%i' % (info['Name'].lstrip('/'), i),
            'tags': [],
            'ttl': 60,
            'attributes': attributes,
            'metric_sint64': x,
        }
        events.append(event)

    # memory_stats
    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s memory limit' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': data['memory_stats']['limit'],
    }
    events.append(event)

    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s memory usage' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': data['memory_stats']['usage'],
    }
    events.append(event)

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
            event = {
                'time': time_,
                'state': 'ok',
                'service': 'container %s memory %s' % (info['Name'].lstrip('/'), k),
                'tags': [],
                'ttl': 60,
                'attributes': attributes,
                'metric_sint64': data['memory_stats']['stats'].get('total_' + k, data['memory_stats']['stats'][k]),
            }
            events.append(event)
        except KeyError:
            # swap
            pass

    # network
    for k, v in data['network'].items():
        event = {
            'time': time_,
            'state': 'ok',
            'service': 'container %s network %s' % (info['Name'].lstrip('/'), k),
            'tags': [],
            'ttl': 60,
            'attributes': attributes,
            'metric_sint64': v,
        }
        events.append(event)

    # precpu_stats

    return events


def write_log(events):
    try:
        with riemann_client.client.QueuedClient(riemann_client.transport.TCPTransport("localhost", 5555)) as client:
            for event in events:
                client.event(**event)
                client.flush()
    except Exception as exc:
        pass
