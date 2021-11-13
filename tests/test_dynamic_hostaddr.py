import asyncio
import json

import pytest

from vidhubcontrol.config import Config
from vidhubcontrol.common import ConnectionState

@pytest.mark.asyncio
async def test_hostaddr_change(tempconfig,
                               vidhub_zeroconf_info,
                               smartview_zeroconf_info,
                               smartscope_zeroconf_info,
                               mocked_vidhub_telnet_device):

    import zeroconf
    from zeroconf.const import _REGISTER_TIME, _UNREGISTER_TIME
    from zeroconf.asyncio import AsyncZeroconf

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
            ev = await asyncio.wait_for(self.queue.get(), timeout=1)
            self.queue.task_done()
            return ev


    PUBLISH_TTL = 5

    publisher = AsyncZeroconf()

    waiter = Waiter()

    config = await Config.load_async(str(tempconfig))
    await config.start()

    waiter.bind(config, 'vidhubs', 'smartviews', 'smartscopes')

    # Publish original addresses
    for zc_data in [vidhub_zeroconf_info, smartview_zeroconf_info, smartscope_zeroconf_info]:
        kwargs = zc_data['info_kwargs']
        info = zeroconf.ServiceInfo(**kwargs)
        info.host_ttl = 5
        await publisher.async_register_service(info)
    await asyncio.sleep(_REGISTER_TIME / 1000 * 3)

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
    for zc_data in [vidhub_zeroconf_info, smartview_zeroconf_info, smartscope_zeroconf_info]:
        kwargs = zc_data['info_kwargs']
        info = zeroconf.ServiceInfo(**kwargs)
        await publisher.async_unregister_service(info)


    await config.stop()
    config = None
    await asyncio.sleep(_UNREGISTER_TIME / 1000 * 3)


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

    state = ConnectionState.failure | ConnectionState.not_connected
    coros = [obj.connection_manager.wait_for('not_connected|failure', 7) for obj in [vidhub, smartview, smartscope]]
    await asyncio.gather(*coros)
    assert vidhub.connection_state == smartview.connection_state == smartscope.connection_state == state

    # Republish correct addresses

    for zc_data in [vidhub_zeroconf_info, smartview_zeroconf_info, smartscope_zeroconf_info]:
        kwargs = zc_data['info_kwargs']
        info = zeroconf.ServiceInfo(**kwargs)
        info.host_ttl = 5
        await publisher.async_register_service(info)

    await asyncio.sleep(_REGISTER_TIME / 1000 * 3)

    coros = [obj.connection_manager.wait_for('connected', 5) for obj in [vidhub, smartview, smartscope]]
    await asyncio.gather(*coros)

    assert vidhub.backend.connection_state == ConnectionState.connected
    assert smartview.backend.connection_state == ConnectionState.connected
    assert smartscope.backend.connection_state == ConnectionState.connected

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

    await publisher.async_close()
