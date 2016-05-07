# events

[![Join the chat at https://gitter.im/mesoscloud/mesoscloud](https://badges.gitter.im/mesoscloud/mesoscloud.svg)](https://gitter.im/mesoscloud/mesoscloud??utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Docker events

## Python

[![](https://badge.imagelayers.io/mesoscloud/events:0.2.2.svg)](https://imagelayers.io/?images=mesoscloud/events:0.2.2)

e.g.

```
docker run -d \
-v /var/run/docker.sock:/var/run/docker.sock \
-v /srv/events:/srv/events \
--name=events --restart=always mesoscloud/events:0.2.2
```

## stats

e.g.

```javascript
{
    "@timestamp": "2015-09-01T06:17:17.847564855Z",

    // container name, id
    "container": "/survival",
    "container_id": "1b4f495e727abbda62698613e0dbcad2184c40413213144286c4b8a34d56d4f0",

    // cpu, flattened
    "cpu_percpu_usage0": 5325369948,
    "cpu_total_usage": 5325369948,
    "cpu_usage_in_kernelmode": 250000000,
    "cpu_usage_in_usermode": 5040000000,

    // image name, id
    "image": "pdericson/minecraft:1.8.8",
    "image_id": "9f62260d81a2f89f605e9f985385cc05a4bcf8c15c1e2b043695a915710761a0",

    // memory, usage and limit are docker specific
    "memory_limit": 1044631552,
    "memory_usage": 358744064,
    // see https://www.kernel.org/doc/Documentation/cgroups/memory.txt for definitions
    // use "total_" instead where present
    "memory_active_anon": 355905536,
    "memory_active_file": 544768,
    "memory_cache": 2330624,
    "memory_inactive_anon": 421888,
    "memory_inactive_file": 1695744,
    "memory_mapped_file": 53248,
    "memory_pgfault": 33779,
    "memory_pgmajfault": 19,
    "memory_pgpgin": 33496,
    "memory_pgpgout": 13906,
    "memory_rss": 356286464,
    "memory_rss_huge": 278921216,
    "memory_swap": 0,
    "memory_unevictable": 0,
    "memory_writeback": 0,

    // network
    "network_rx_bytes": 578,
    "network_rx_dropped": 0,
    "network_rx_errors": 0,
    "network_rx_packets": 7,
    "network_tx_bytes": 668,
    "network_tx_dropped": 0,
    "network_tx_errors": 0,
    "network_tx_packets": 8
}
```

References:

- https://www.kernel.org/doc/Documentation/cgroups/memory.txt
- https://docs.docker.com/articles/runmetrics/
