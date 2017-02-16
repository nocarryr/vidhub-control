import asyncio
import pytest

@pytest.mark.asyncio
async def test_to_see_if_app_can_run(kivy_app):
    print('test_to_see_if_app_can_run', '*'*20)
    def on_app_vidhubs(*args):
        print('vidhubs: ', args)
    print('binding stuff')
    kivy_app.bind(vidhubs=on_app_vidhubs)
    print('running()')
    kivy_app.run()
    print('run complete')
    await asyncio.sleep(1)
    print('stopping')
    await kivy_app.stop_async()


@pytest.mark.asyncio
async def test_vidhub_dropdown(kivy_app):
    print('test_vidhub_dropdown', '*'*20)
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
    #await kivy_app.start_async()
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config
    print('root widget: ', kivy_app.root)
    print('root children: ', kivy_app.root.children)
    dropdown = kivy_app.root.header_widget.vidhub_dropdown
    assert len(dropdown.btns) == 0

    kv_waiter.bind(dropdown, 'btns')
    vidhub = await DummyBackend.create_async(device_id='dummy1', device_name='Dummy 1')
    config.add_vidhub(vidhub)
    await kv_waiter.wait()
    kv_waiter.unbind(dropdown, 'btns')

    assert 'dummy1' in dropdown.btns
    btn = dropdown.btns['dummy1']
    assert btn.text == 'Dummy 1'
    print('btn: ', btn)

    kv_waiter.bind(kivy_app, 'selected_vidhub')
    btn.dispatch('on_release')
    await kv_waiter.wait()

    assert kivy_app.selected_vidhub is vidhub
    print(kivy_app.selected_vidhub)

    print('stopping')
    await kivy_app.stop_async()
