import copy
import datetime
import re
import shlex

import riemann_client.client

__all__ = ['handle_log', 'handle_stat']


def handle_log(line, info, stream=None):
    """Handle a line of log output

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
        >>> event['attributes']['@timestamp']
        '2015-08-31T14:41:43Z'

        >>> line = b"Error running logs job:"
        >>> info = {'Id': '', 'Image': '', 'Name': 'foo', 'Config': {'Image': '', 'Cmd': [], 'Entrypoint': ''}}

        >>> events = handle_log(line, info)

    """
    # https://github.com/docker/docker/blob/87e7ee914261efd2580accae98569466f42cd003/api/server/router/container/container_routes.go#L148
    if line.startswith(b"Error running logs job:"):
        return []

    a = stream if stream is not None else 'stdout'

    m = re.search(rb'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{9}Z ', line)

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
            '@timestamp': b.decode('utf-8').split('.')[0]+'Z',
        },
    }

    return [event]


def handle_stat(data, info):
    """Handle stat

        >>> blkio_stats = {}
        >>> cpu_stats = {'cpu_usage': {'total_usage': 0, 'usage_in_kernelmode': 0, 'usage_in_usermode': 0, 'percpu_usage': []}}
        >>> memory_stats = {'limit': 256 * 1024 * 1024, 'usage': 128 * 1024 * 1024}
        >>> network = {}
        >>> data = {'read': '2015-09-23T04:13:56.297129480Z', 'blkio_stats': blkio_stats, 'cpu_stats': cpu_stats, 'memory_stats': memory_stats, 'network': network}
        >>> info = {'Name': 'foo', 'Id': '123', 'Config': {'Image': 'centos:7', 'Cmd': ['true'], 'Entrypoint': ''}, 'Image': 'abc'}
        >>> events = handle_stat(data, info)

        >>> len(events)
        4
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
        >>> event['attributes']['@timestamp']
        '2015-09-23T04:13:56Z'

    """

    events = []

    time_ = int((datetime.datetime.strptime(data['read'].split('.')[0], '%Y-%m-%dT%H:%M:%S') - datetime.datetime(1970,1,1)).total_seconds())

    attributes = {
        'container': info['Name'].lstrip('/'),
        'container_id': info['Id'],
        'image': info['Config']['Image'],
        'image_id': info['Image'],
        'container_cmd': ' '.join([shlex.quote(x) for x in (info['Config']['Cmd'] if info['Config']['Cmd'] is not None else [])]),
        '@timestamp': data['read'].split('.')[0]+'Z',
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

#    event = {
#        'time': time_,
#        'state': 'ok',
#        'service': 'container %s cpu usage in kernelmode' % info['Name'].lstrip('/'),
#        'tags': [],
#        'ttl': 60,
#        'attributes': attributes,
#        'metric_sint64': data['cpu_stats']['cpu_usage']['usage_in_kernelmode'],
#    }
#    events.append(event)
#
#    event = {
#        'time': time_,
#        'state': 'ok',
#        'service': 'container %s cpu usage in usermode' % info['Name'].lstrip('/'),
#        'tags': [],
#        'ttl': 60,
#        'attributes': attributes,
#        'metric_sint64': data['cpu_stats']['cpu_usage']['usage_in_usermode'],
#    }
#    events.append(event)
#
#    if data['cpu_stats']['cpu_usage']['percpu_usage'] is not None:
#        for i, x in enumerate(data['cpu_stats']['cpu_usage']['percpu_usage']):
#            event = {
#                'time': time_,
#                'state': 'ok',
#                'service': 'container %s cpu usage in cpu%i' % (info['Name'].lstrip('/'), i),
#                'tags': [],
#                'ttl': 60,
#                'attributes': attributes,
#                'metric_sint64': x,
#            }
#            events.append(event)

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

    event = {
        'time': time_,
        'state': 'ok',
        'service': 'container %s memory usage percent' % info['Name'].lstrip('/'),
        'tags': [],
        'ttl': 60,
        'attributes': attributes,
        'metric_sint64': int(round(float(data['memory_stats']['usage']) / float(data['memory_stats']['limit']) * 100.0)),
    }
    events.append(event)

    # https://www.kernel.org/doc/Documentation/cgroups/memory.txt
    for k in [
#            'active_anon',
#            'active_file',
            'cache',
            #'hierarchical_memory_limit',
            #'hierarchical_memsw_limit',
#            'inactive_anon',
#            'inactive_file',
#            'mapped_file',
#            'pgfault',
#            'pgmajfault',
#            'pgpgin',
#            'pgpgout',
            'rss',
#            'rss_huge',
            'swap',
#            'unevictable',
#            'writeback',
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
    if 'network' in data:
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
