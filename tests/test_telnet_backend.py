import asyncio
import pytest

from vidhubcontrol.backends import telnet
from vidhubcontrol.backends.telnet import TelnetBackend, SmartScopeTelnetBackend

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
    mocked_vidhub_telnet_device.preamble = 'smartscope'

    backend = await SmartScopeTelnetBackend.create_async(hostaddr=True)

    assert backend.prelude_parsed

    assert backend.device_model == 'SmartScope Duo 4K'
    assert backend.device_name == 'SmartScope Duo'
    assert backend.device_id.lower() == '0a1b2c3d4e5f'
    assert not backend.inverted
    assert backend.num_monitors == len(backend.monitors) == 2

    monitor = backend.monitors[0]
    assert monitor.name == 'MONITOR A'
    assert monitor.brightness == 255
    assert monitor.contrast == 128

    await backend.disconnect()
