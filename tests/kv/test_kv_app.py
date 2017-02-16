import asyncio
import pytest


@pytest.mark.asyncio
async def test_vidhub_dropdown(kivy_app):
    from vidhubcontrol.backends import DummyBackend

    class KvEventWaiter(object):
        def __init__(self):
            self.aio_event = asyncio.Event()
        def bind(self, obj, *events):
            kwargs = {e:self.kivy_callback for e in events}
            obj.bind(**kwargs)
        def unbind(self, obj, *events):
            kwargs = {e:self.kivy_callback for e in events}
            obj.unbind(**kwargs)
        async def wait(self):
            await self.aio_event.wait()
            self.aio_event.clear()
        async def bind_and_wait(self, obj, *events):
            self.aio_event.clear()
            self.bind(obj, *events)
            await self.wait()
        def kivy_callback(self, *args, **kwargs):
            self.aio_event.set()

    kv_waiter = KvEventWaiter()
    kv_waiter.bind(kivy_app, 'on_start')
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config
    dropdown = kivy_app.root.header_widget.vidhub_dropdown
    assert len(dropdown.btns) == 0

    kv_waiter.bind(dropdown, 'btns')
    vidhub1 = await DummyBackend.create_async(device_id='dummy1', device_name='Dummy 1')
    vidhub2 = await DummyBackend.create_async(device_id='dummy2', device_name='Dummy 2')
    config.add_vidhub(vidhub1)
    await kv_waiter.wait()
    config.add_vidhub(vidhub2)
    await kv_waiter.wait()
    kv_waiter.unbind(dropdown, 'btns')

    assert 'dummy1' in dropdown.btns
    assert 'dummy2' in dropdown.btns
    btn = dropdown.btns['dummy1']
    assert btn.vidhub is vidhub1
    assert btn.text == vidhub1.device_name == 'Dummy 1'

    kv_waiter.bind(kivy_app, 'selected_vidhub')
    btn.dispatch('on_release')
    await kv_waiter.wait()

    assert kivy_app.selected_vidhub is vidhub1

    await kivy_app.wait_for_widget_init()

    btn = dropdown.btns['dummy2']
    assert btn.vidhub is vidhub2
    assert btn.text == vidhub2.device_name == 'Dummy 2'

    assert not kv_waiter.aio_event.is_set()
    btn.dispatch('on_release')
    await kv_waiter.wait()
    assert kivy_app.selected_vidhub is vidhub2

    await kivy_app.stop_async()
