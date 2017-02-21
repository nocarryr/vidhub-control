import asyncio
import pytest

@pytest.mark.asyncio
async def test_prop_setters():
    from vidhubcontrol.backends import DummyBackend

    vidhub = await DummyBackend.create_async()

    class Waiter(object):
        def __init__(self):
            self._event = asyncio.Event()
        def bind(self, event_name):
            vidhub.bind(**{event_name:self.on_event})
        def unbind(self):
            vidhub.unbind(self)
        def on_event(self, *args, **kwargs):
            self._event.set()
        async def wait(self):
            await self._event.wait()
            self._event.clear()

    waiter = Waiter()

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
