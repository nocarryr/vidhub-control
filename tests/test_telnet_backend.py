import ipaddress
import asyncio
import pytest

from vidhubcontrol.backends import telnet
from vidhubcontrol.backends.telnet import TelnetBackend, SmartViewTelnetBackend, SmartScopeTelnetBackend

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


@pytest.fixture(params=['smartview', 'smartscope'])
def smartview_backend(request, mocked_vidhub_telnet_device):
    d = {'backend_name':request.param, 'kwargs':{'hostaddr':True}}
    if request.param == 'smartview':
        d['cls'] = SmartViewTelnetBackend
        d['kwargs']['hostport'] = 9991
        d.update({
            'device_id':'a10203040506',
            'device_model':'SmartView Something',
            'device_name':'SmartView Something',
            'using_dhcp':True,
            'static_ip':ipaddress.ip_interface('192.168.0.3/255.255.255.0'),
            'static_gateway':ipaddress.ip_address('192.168.0.1'),
            'current_ip':ipaddress.ip_interface('192.168.1.101/255.255.255.0'),
            'current_gateway':ipaddress.ip_address('192.168.1.1'),
        })
    elif request.param == 'smartscope':
        d['cls'] = SmartScopeTelnetBackend
        d['kwargs']['hostport'] = 9992
        d.update({
            'device_id':'0a1b2c3d4e5f',
            'device_model':'SmartScope Duo 4K',
            'device_name':'SmartScope Duo',
            'using_dhcp':True,
            'static_ip':ipaddress.ip_interface('192.168.0.2/255.255.255.0'),
            'static_gateway':ipaddress.ip_address('192.168.0.1'),
            'current_ip':ipaddress.ip_interface('192.168.1.100/255.255.255.0'),
            'current_gateway':ipaddress.ip_address('192.168.1.1'),
        })
    return d

@pytest.mark.asyncio
async def test_telnet_smartscope(smartview_backend):
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    backend = await smartview_backend['cls'].create_async(**smartview_backend['kwargs'])
    waiter = AsyncEventWaiter(backend)

    assert backend.prelude_parsed

    assert backend.device_model == smartview_backend['device_model']
    assert backend.device_name == smartview_backend['device_name']
    assert backend.device_id.lower() == smartview_backend['device_id']
    assert backend.using_dhcp == smartview_backend['using_dhcp']
    assert backend.static_ip == smartview_backend['static_ip']
    assert backend.static_gateway == smartview_backend['static_gateway']
    assert backend.current_ip == smartview_backend['current_ip']
    assert backend.current_gateway == smartview_backend['current_gateway']
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

        if smartview_backend['backend_name'] == 'smartscope':
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
