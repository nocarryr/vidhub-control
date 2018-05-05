import asyncio
import json

import pytest

from vidhubcontrol.config import Config

@pytest.mark.asyncio
async def test_hostaddr_change(tempconfig,
                               vidhub_zeroconf_info,
                               smartview_zeroconf_info,
                               smartscope_zeroconf_info,
                               mocked_vidhub_telnet_device):

    class Waiter(object):
        def __init__(self):
            self.queue = asyncio.Queue()
        def bind(self, obj, *event_names):
            for event_name in event_names:
                obj.bind(**{event_name:self.on_event})
        def unbind(self, obj):
            obj.unbind(self)
        def on_event(self, *args, **kwargs):
            self.queue.put_nowait((args, kwargs))
        async def wait(self):
            ev = await self.queue.get()
            self.queue.task_done()
            return ev


    PUBLISH_TTL = 5

    waiter = Waiter()

    config = await Config.load_async(str(tempconfig))
    await config.start()

    waiter.bind(config, 'vidhubs', 'smartviews', 'smartscopes')

    # Publish original addresses
    args, kwargs = [vidhub_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartview_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartscope_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config.discovery_listener.publish_service(*args, **kwargs)

    events_received = 0
    while events_received < 3:
        await waiter.wait()
        events_received += 1

    vidhub_id = vidhub_zeroconf_info['device_id']
    smartview_id = smartview_zeroconf_info['device_id']
    smartscope_id = smartscope_zeroconf_info['device_id']

    assert vidhub_id in config.vidhubs
    assert smartview_id in config.smartviews
    assert smartscope_id in config.smartscopes

    # Unpublish
    args, kwargs = [vidhub_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    del kwargs['ttl']
    await config.discovery_listener.unpublish_service(*args, **kwargs)

    args, kwargs = [smartview_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    del kwargs['ttl']
    await config.discovery_listener.unpublish_service(*args, **kwargs)

    args, kwargs = [smartscope_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    del kwargs['ttl']
    await config.discovery_listener.unpublish_service(*args, **kwargs)

    await config.stop()
    config = None
    await asyncio.sleep(PUBLISH_TTL)


    # Alter saved conf data with false address info
    with open(str(tempconfig), 'r') as f:
        conf_str = f.read()
    conf_data = json.loads(conf_str)

    conf_data['vidhubs'][vidhub_id]['hostaddr'] = '0.0.0.0'
    conf_data['smartviews'][smartview_id]['hostaddr'] = '0.0.0.0'
    conf_data['smartscopes'][smartscope_id]['hostaddr'] = '0.0.0.0'

    conf_str = json.dumps(conf_data, indent=2)
    with open(str(tempconfig), 'w') as f:
        f.write(conf_str)


    # Load saved config from above
    config2 = await Config.load_async(str(tempconfig))
    await config2.start()

    vidhub = config2.vidhubs[vidhub_id]
    smartview = config2.smartviews[smartview_id]
    smartscope = config2.smartscopes[smartscope_id]

    assert vidhub.backend_unavailable is True
    assert smartview.backend_unavailable is True
    assert smartscope.backend_unavailable is True


    # Republish correct addresses
    waiter2 = Waiter()
    waiter2.bind(vidhub.backend, 'connected')
    waiter2.bind(smartview.backend, 'connected')
    waiter2.bind(smartscope.backend, 'connected')

    args, kwargs = [vidhub_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config2.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartview_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config2.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartscope_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    kwargs['ttl'] = 5
    await config2.discovery_listener.publish_service(*args, **kwargs)

    events_received = 0
    while events_received < 3:
        await waiter2.wait()
        events_received += 1

    assert vidhub.backend.connected
    assert smartview.backend.connected
    assert smartscope.backend.connected

    assert vidhub.hostaddr == '127.0.0.1'
    assert smartview.hostaddr == '127.0.0.1'
    assert smartscope.hostaddr == '127.0.0.1'

    assert vidhub.backend is not None
    assert smartview.backend is not None
    assert smartscope.backend is not None

    assert config2.vidhubs[vidhub_id] is vidhub
    assert config2.smartviews[smartview_id] is smartview
    assert config2.smartscopes[smartscope_id] is smartscope

    await config2.stop()
