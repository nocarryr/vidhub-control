import asyncio

import pytest

from vidhubcontrol.config import Config

@pytest.mark.asyncio
async def test_config_basic(tempconfig, missing_netifaces):
    from vidhubcontrol.backends import DummyBackend

    config = await Config.load_async(str(tempconfig))
    await config.start()

    vidhub = await DummyBackend.create_async(device_id=None)
    await config.add_vidhub(vidhub)
    temp_id = config.id_for_device(vidhub)
    assert config.vidhubs[temp_id].backend == vidhub

    vidhub.device_id = 'dummy1'
    await asyncio.sleep(.1)
    assert config.vidhubs['dummy1'].backend == vidhub
    assert temp_id not in config.vidhubs

    preset1 = await vidhub.store_preset(name='PRESET1')

    assert config.vidhubs['dummy1'].presets[0] == {
        'name':'PRESET1',
        'index':0,
        'crosspoints':{i:0 for i in range(vidhub.num_outputs)},
    }

    await vidhub.set_crosspoint(0, 12)

    preset8 = await vidhub.store_preset(name='PRESET8', index=8, outputs_to_store=[0])

    assert config.vidhubs['dummy1'].presets[8] == {
        'name':'PRESET8',
        'index':8,
        'crosspoints':{0:12},
    }

    config2 = await Config.load_async(str(tempconfig))
    await config2.start()

    attrs = config.vidhubs['dummy1']._conf_attrs
    for attr in attrs:
        if attr == 'presets':
            continue
        assert getattr(config2.vidhubs['dummy1'], attr) == getattr(config.vidhubs['dummy1'], attr)

    preset1_2 = config2.vidhubs['dummy1'].backend.presets[0]
    preset8_2 = config2.vidhubs['dummy1'].backend.presets[8]

    for attr in ['name', 'index', 'crosspoints']:
        assert getattr(preset1, attr) == getattr(preset1_2, attr)
        assert getattr(preset8, attr) == getattr(preset8_2, attr)

    await config.stop()
    await config2.stop()

@pytest.mark.asyncio
async def test_config_discovery(tempconfig,
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
    waiter = Waiter()

    config = await Config.load_async(str(tempconfig))
    await config.start()

    waiter.bind(config, 'vidhubs', 'smartviews', 'smartscopes')

    args, kwargs = [vidhub_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    await config.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartview_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    await config.discovery_listener.publish_service(*args, **kwargs)

    args, kwargs = [smartscope_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    await config.discovery_listener.publish_service(*args, **kwargs)

    events_received = 0
    while events_received < 3:
        await waiter.wait()
        events_received += 1

    assert vidhub_zeroconf_info['device_id'] in config.vidhubs
    assert smartview_zeroconf_info['device_id'] in config.smartviews
    assert smartscope_zeroconf_info['device_id'] in config.smartscopes

    await config.stop()


@pytest.mark.asyncio
async def test_config_devices(tempconfig, missing_netifaces):
    from vidhubcontrol.backends import (
        DummyBackend, SmartViewDummyBackend, SmartScopeDummyBackend,
    )

    config = await Config.load_async(str(tempconfig))
    await config.start()

    for i in range(3):
        device_id = 'dummy{}'.format(i)
        vidhub = await DummyBackend.create_async(
            device_id=device_id,
            device_name='vidhub{}'.format(i),
        )
        smartview = await SmartViewDummyBackend.create_async(
            device_id=device_id,
            device_name='smartview{}'.format(i),
        )
        smartscope = await SmartScopeDummyBackend.create_async(
            device_id=device_id,
            device_name='smartscope{}'.format(i)
        )
        if i == 0:
            await config.add_vidhub(vidhub)
            await config.add_smartview(smartview)
            await config.add_smartscope(smartscope)
        else:
            await config.add_device(vidhub)
            await config.add_device(smartview)
            await config.add_device(smartscope)

    keys_expected = set(('dummy{}'.format(i) for i in range(3)))
    assert len(config.vidhubs) == len(config.smartviews) == len(config.smartscopes) == 3
    assert set(config.vidhubs.keys()) == set(config.smartviews.keys()) == set(config.smartscopes.keys()) == keys_expected

    for vidhub in config.vidhubs.values():
        assert isinstance(vidhub.backend, DummyBackend)
    for smartview in config.smartviews.values():
        assert isinstance(smartview.backend, SmartViewDummyBackend)
    for smartscope in config.smartscopes.values():
        assert isinstance(smartscope.backend, SmartScopeDummyBackend)

    config2 = await Config.load_async(str(tempconfig))
    await config2.start()

    assert len(config2.vidhubs) == len(config2.smartviews) == len(config2.smartscopes) == 3
    assert set(config2.vidhubs.keys()) == set(config2.smartviews.keys()) == set(config2.smartscopes.keys()) == keys_expected

    for vidhub in config2.vidhubs.values():
        assert isinstance(vidhub.backend, DummyBackend)
    for smartview in config2.smartviews.values():
        assert isinstance(smartview.backend, SmartViewDummyBackend)
    for smartscope in config2.smartscopes.values():
        assert isinstance(smartscope.backend, SmartScopeDummyBackend)

    await config.stop()
    await config2.stop()
