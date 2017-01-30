import asyncio

import pytest

from vidhubcontrol.config import Config

@pytest.mark.asyncio
async def test_config_basic(tempconfig):
    from vidhubcontrol.backends.dummy import DummyBackend

    config = Config.load(str(tempconfig))
    await config.start()

    vidhub = await DummyBackend.create_async(device_id=None)
    config.add_vidhub(vidhub)
    assert config.vidhubs[id(vidhub)].backend == vidhub

    vidhub.device_id = 'dummy1'
    assert config.vidhubs['dummy1'].backend == vidhub
    assert id(vidhub) not in config.vidhubs

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

    config2 = Config.load(str(tempconfig))
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

@pytest.mark.asyncio
async def test_config_discovery(tempconfig, vidhub_zeroconf_info, mocked_vidhub_telnet_device):

    config = Config.load(str(tempconfig))
    await config.start()

    args, kwargs = [vidhub_zeroconf_info[key] for key in ['info_args', 'info_kwargs']]
    await config.discovery_listener.publish_service(*args, **kwargs)

    await asyncio.sleep(1)

    assert vidhub_zeroconf_info['device_id'] in config.vidhubs

    await config.stop()
