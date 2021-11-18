import asyncio
import pytest

from vidhubcontrol.backends import telnet
from vidhubcontrol.backends.telnet import TelnetBackend, SmartViewTelnetBackend, SmartScopeTelnetBackend
from vidhubcontrol.common import ConnectionState

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
@pytest.mark.parametrize('backend_name', ['smartview', 'smartscope'])
async def test_telnet_smartscope(backend_name, telnet_backend_factory):
    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    backend_data = telnet_backend_factory(backend_name)
    backend = await backend_data['cls'].create_async(**backend_data['kwargs'])
    waiter = AsyncEventWaiter(backend)

    assert backend.prelude_parsed

    assert backend.device_model == backend_data['device_model']
    assert backend.device_name == backend_data['device_name']
    assert backend.device_id.lower() == backend_data['device_id']
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

        if backend_name == 'smartscope':
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


class StateListener:
    def __init__(self, manager):
        self.states = []
        self.manager = manager
        self.running = False
        self.task = None
        self.task_ready = asyncio.Event()

    async def run(self):
        self.task_ready.set()

        all_states = ConnectionState.not_connected
        for member in ConnectionState:
            all_states |= member

        post_state = None
        while self.running:
            pre_state = self.manager.state
            if post_state is not None:
                assert pre_state == post_state
            async with self.manager:
                cur_state = self.manager.state
                if pre_state != cur_state:
                    self.states.append(cur_state)
                wait_state = all_states ^ cur_state
                try:
                    state = await self.manager.wait_for(wait_state, .1)
                    self.states.append(state)
                    assert self.manager.state == state
                    cur_state = state
                except asyncio.TimeoutError:
                    pass
            post_state = self.manager.state
            assert cur_state == post_state

    async def open(self):
        if self.running:
            return
        assert self.task is None
        self.running = True
        self.task_ready.clear()
        self.task = asyncio.ensure_future(self.run())
        await self.task_ready.wait()

    async def close(self):
        if not self.running:
            return
        self.running = False
        t = self.task
        self.task = None
        if t is not None:
            await t
        self.task_ready.clear()

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('backend_name', ['vidhub', 'smartview', 'smartscope'])
async def test_connect_called_while_connecting(backend_name, telnet_backend_factory):
    backend_data = telnet_backend_factory(backend_name)
    backend = backend_data['cls'](**backend_data['kwargs'])

    connect_evt = asyncio.Event()
    disconnect_evt = asyncio.Event()
    async def connect():
        connect_evt.set()
        return await backend.connect()
    async def disconnect():
        disconnect_evt.set()
        await backend.disconnect()


    listener = StateListener(backend.connection_manager)
    async with listener:
        connect_task = asyncio.ensure_future(connect())
        await connect_evt.wait()
        result = await backend.connect()
        task_result = await connect_task
        assert result is task_result is backend.client
        assert backend.connection_state == ConnectionState.connected
        assert backend.prelude_parsed

        disconnect_task = asyncio.ensure_future(disconnect())
        await disconnect_evt.wait()
        await backend.disconnect()
        assert backend.connection_state == ConnectionState.not_connected
        await disconnect_task
        assert backend.connection_state == ConnectionState.not_connected

    states_expected = [
        ConnectionState.connecting,
        ConnectionState.connected,
        ConnectionState.disconnecting,
        ConnectionState.not_connected,
    ]
    assert listener.states == states_expected


@pytest.mark.asyncio
@pytest.mark.parametrize('backend_name', ['vidhub', 'smartview', 'smartscope'])
async def test_disconnect_called_while_connecting(backend_name, telnet_backend_factory):
    backend_data = telnet_backend_factory(backend_name)
    backend = backend_data['cls'](**backend_data['kwargs'])

    listener = StateListener(backend.connection_manager)
    async with listener:
        connect_task = asyncio.ensure_future(backend.connect())
        async with backend.connection_manager as mgr:
            await mgr.wait_for('connecting')
        print('connecting')
        assert backend.connection_state == ConnectionState.connecting

        print('disconnecting')
        await backend.disconnect()

        async with backend.connection_manager as mgr:
            await mgr.wait_for('not_connected')
        assert backend.connection_state == ConnectionState.not_connected

        await connect_task
        assert backend.connection_state == ConnectionState.not_connected

    states_expected = [
        ConnectionState.connecting,
        ConnectionState.connected,
        ConnectionState.disconnecting,
        ConnectionState.not_connected,
    ]

    states = listener.states
    assert states == states_expected

@pytest.mark.asyncio
@pytest.mark.parametrize('backend_name', ['vidhub', 'smartview', 'smartscope'])
async def test_connect_called_while_disconnecting(backend_name, telnet_backend_factory):
    backend_data = telnet_backend_factory(backend_name)
    backend = backend_data['cls'](**backend_data['kwargs'])

    connect_evt = asyncio.Event()
    disconnect_evt = asyncio.Event()
    async def connect():
        connect_evt.set()
        return await backend.connect()
    async def disconnect():
        await disconnect_evt.wait()
        await backend.disconnect()

    listener = StateListener(backend.connection_manager)
    async with listener:
        await backend.connect()
        assert backend.connection_state == ConnectionState.connected

        disconnect_task = asyncio.ensure_future(disconnect())
        async with backend.connection_manager as mgr:
            assert backend.connection_state == ConnectionState.connected
            disconnect_evt.set()
            await mgr.wait_for('disconnecting')
            assert backend.connection_state == ConnectionState.disconnecting

        print('reconnect')
        await backend.connect()
        await disconnect_task
        assert backend.connection_state == ConnectionState.connected
        await asyncio.sleep(0)
        await backend.disconnect()

    states_expected = [
        ConnectionState.connecting,
        ConnectionState.connected,
        ConnectionState.disconnecting,
        ConnectionState.not_connected,
        ConnectionState.connecting,
        ConnectionState.connected,
        ConnectionState.disconnecting,
        ConnectionState.not_connected,
    ]
    states = listener.states
    assert states == states_expected
