import asyncio
import pytest

from vidhubcontrol.backends import telnet
from vidhubcontrol.backends.telnet import TelnetBackend, SmartScopeTelnetBackend

from utils import AsyncEventWaiter

@pytest.mark.asyncio
async def test_telnet_vidhub(mocked_vidhub_telnet_device, vidhub_telnet_responses):

    backend = await TelnetBackend.create_async(hostaddr=True)

    assert backend.prelude_parsed

    assert backend.num_outputs == len(backend.crosspoints) == len(backend.output_labels)
    assert backend.num_inputs == len(backend.input_labels)

    for in_idx in range(backend.num_inputs):
        crosspoints = [in_idx]*backend.num_outputs
        await backend.set_crosspoints(*((i, val) for i, val in enumerate(crosspoints)))
        assert backend.crosspoints == crosspoints

    for s in ['foo, bar, baz']:
        in_lbls = ['{} {}'.format(s, i) for i in range(backend.num_inputs)]
        out_lbls = ['{} {}'.format(s, i) for i in range(backend.num_outputs)]
        await backend.set_input_labels(*((i, lbl) for i, lbl in enumerate(in_lbls)))
        await backend.set_output_labels(*((i, lbl) for i, lbl in enumerate(out_lbls)))
        assert backend.input_labels == in_lbls
        assert backend.output_labels == out_lbls

    await backend.disconnect()

@pytest.mark.asyncio
async def test_telnet_smartscope(mocked_vidhub_telnet_device):
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    backend = await SmartScopeTelnetBackend.create_async(hostaddr=True)
    waiter = AsyncEventWaiter(backend)

    assert backend.prelude_parsed

    assert backend.device_model == 'SmartScope Duo 4K'
    assert backend.device_name == 'SmartScope Duo'
    assert backend.device_id.lower() == '0a1b2c3d4e5f'
    assert not backend.inverted
    assert backend.num_monitors == len(backend.monitors) == 2

    waiter.bind('on_monitor_property_change')

    async def set_and_check_monitor_prop(obj, prop_name, prop_val):
        print('{}: setting {} to {}, current={}'.format(obj.name, prop_name, prop_val, getattr(obj, prop_name)))
        setattr(obj, prop_name, prop_val)
        args, kwargs = await waiter.wait()
        _, event_name, event_value = args
        assert kwargs['monitor'] is obj
        assert event_name == prop
        assert event_value == prop_val == getattr(obj, prop)

    defaults = {
        'brightness':255,
        'contrast':128,
        'saturation':128,
        'identify':False,
        'border':None,
        'widescreen_sd':None,
        'audio_channel':0,
    }
    default_scopes = ['waveform', 'vector_100']

    for i, name, monitor in zip(range(2), ['MONITOR A', 'MONITOR B'], backend.monitors):
        assert monitor.index == i
        assert monitor.name == name

        for key, val in defaults.items():
            assert getattr(monitor, key) == val
        assert monitor.scope_mode == default_scopes[i]

        props = monitor.PropertyChoices._bind_properties
        for prop in props:
            choices = monitor.get_property_choices(prop)
            if choices is not None:
                for prop_val, device_val in choices.items():
                    if getattr(monitor, prop) == prop_val:
                        continue
                    await set_and_check_monitor_prop(monitor, prop, prop_val)
            elif prop == 'identify':
                assert isinstance(monitor.identify, bool)
                prop_val = not monitor.identify
                await set_and_check_monitor_prop(monitor, prop, prop_val)
            else:
                for i in range(100):
                    if getattr(monitor, prop) == i:
                        continue
                    await set_and_check_monitor_prop(monitor, prop, i)
                    setattr(monitor, prop, i)

    waiter.unbind()

    await backend.disconnect()
