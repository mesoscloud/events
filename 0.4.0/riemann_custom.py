import copy
import re


def glog(event):
    """Parse severity from Google Log (glog) output

    >>> event = {'attributes': {'container': 'chronos', 'stream': 'stderr'}, 'state': 'ok'}
    >>> event['attributes']['log'] = '''E1013 02:44:56.495528    13 slave.cpp:3301] Container 'd94c2386-84cf-4fcb-86fb-698aecaac1ee' for executor 'ct:1444704240000:0:dockerjob:' of framework '20151007-123458-1724154890-5050-1-0001' failed to start: Failed to 'docker pull does-not-exist:latest': exit status = exited with status 1 stderr = Error: image library/does-not-exist:latest not found'''
    >>> glog(event)['state']
    'error'

    """
    if event['attributes'].get('stream') == 'stderr':
        m = re.match(r'(.)[0-9]{4} [0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]{6}\s+[0-9]+ .*?:[0-9]+\] .*', event['attributes']['log'])
        if m:
            severity = {
                'I': 'info',
                'W': 'warning',
                'E': 'error',
                'F': 'fatal',
            }
            if m.group(1) in severity:
                event['state'] = severity[m.group(1)]

    return event
