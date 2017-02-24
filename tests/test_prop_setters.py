import asyncio
import pytest

class Waiter(object):
    def __init__(self, device):
        self.device = device
        self._event = asyncio.Event()
        self._lock = asyncio.Lock()
        self.args = None
        self.kwargs = None
    def bind(self, event_name):
        self.device.bind(**{event_name:self.on_event})
    def unbind(self):
        self.device.unbind(self)
    def on_event(self, *args, **kwargs):
        async def trigger(_args, _kwargs):
            async with self._lock:
                self.args = _args
                self.kwargs = _kwargs
            self._event.set()
        asyncio.ensure_future(trigger(args, kwargs))
    async def wait(self):
        await self._event.wait()
        async with self._lock:
            args, kwargs = self.args, self.kwargs
            self.args = None
            self.kwargs = None
        self._event.clear()
        return args, kwargs

@pytest.mark.asyncio
async def test_prop_setters():
    from vidhubcontrol.backends import DummyBackend

    vidhub = await DummyBackend.create_async()

    waiter = Waiter(vidhub)

    waiter.bind('input_labels')
    for i in range(vidhub.num_inputs):
        lbl = 'Input FOO {}'.format(i)
        print('setting input label {} to {}'.format(i, lbl))
        vidhub.input_label_control[i] = lbl
        await waiter.wait()

        assert vidhub.input_labels[i] == lbl

    lbls = ['Input BAR {}'.format(i) for i in range(vidhub.num_inputs)]
    print('setting multiple input_labels')
    vidhub.input_label_control = lbls
    await waiter.wait()

    assert vidhub.input_labels == lbls

    waiter.unbind()

    waiter.bind('output_labels')
    for i in range(vidhub.num_outputs):
        lbl = 'Output FOO {}'.format(i)
        print('setting output label {} to {}'.format(i, lbl))
        vidhub.output_label_control[i] = lbl
        await waiter.wait()

        assert vidhub.output_labels[i] == lbl

    lbls = ['Output BAR {}'.format(i) for i in range(vidhub.num_outputs)]
    vidhub.output_label_control = lbls
    await waiter.wait()

    assert vidhub.output_labels == lbls

    waiter.unbind()

    await vidhub.set_crosspoints(*((i, 0) for i in range(vidhub.num_outputs)))
    print(vidhub.crosspoints)

    waiter.bind('crosspoints')
    for in_idx in range(vidhub.num_inputs):
        for out_idx in range(vidhub.num_outputs):
            if vidhub.crosspoints[out_idx] == in_idx:
                print('crosspoint {} == {}, skipping'.format(out_idx, in_idx))
                continue
            print('setting crosspoint {} to {}'.format(out_idx, in_idx))
            vidhub.crosspoint_control[out_idx] = in_idx
            await waiter.wait()

            assert vidhub.crosspoints[out_idx] == in_idx
            assert vidhub.crosspoints == vidhub.crosspoint_control

        xpts = list(range(vidhub.num_outputs))
        print('setting all crosspoints to {}'.format(xpts))
        vidhub.crosspoint_control = xpts
        await waiter.wait()

        assert vidhub.crosspoints == vidhub.crosspoint_control == xpts

    waiter.unbind()

    await vidhub.disconnect()

@pytest.mark.asyncio
async def test_smartscope_prop_setters():
    from vidhubcontrol.backends import SmartScopeDummyBackend


    scope = await SmartScopeDummyBackend.create_async()
    waiter = Waiter(scope)
    waiter.bind('on_monitor_property_change')

    async def set_and_check_monitor_prop(obj, prop_name, prop_val):
        print('{}: setting {} to {}, current={}'.format(obj.name, prop_name, prop_val, getattr(obj, prop_name)))
        setattr(obj, prop_name, prop_val)
        args, kwargs = await waiter.wait()
        _, event_name, event_value = args
        assert kwargs['monitor'] is obj
        assert event_name == prop
        assert event_value == prop_val == getattr(obj, prop)

    assert len(scope.monitors) == 2

    for i, name, monitor in zip(range(2), ['MONITOR A', 'MONITOR B'], scope.monitors):
        assert monitor.index == i
        assert monitor.name == name
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
                for i in range(20):
                    if getattr(monitor, prop) == i:
                        continue
                    await set_and_check_monitor_prop(monitor, prop, i)
                    setattr(monitor, prop, i)

    waiter.unbind()

    await scope.disconnect()
