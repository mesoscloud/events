# events

[![Join the chat at https://gitter.im/mesoscloud/events](https://badges.gitter.im/Join%20Chat.svg)](https://gitter.im/mesoscloud/events?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge)

Docker events

## Python

[![](https://badge.imagelayers.io/mesoscloud/events:0.1.1.svg)](https://imagelayers.io/?images=mesoscloud/events:0.1.1)

e.g.

```
docker run -d \
-v /var/run/docker.sock:/var/run/docker.sock \
-v /srv/events:/srv/events \
--name=events --restart=always mesoscloud/events:0.1.1
```
