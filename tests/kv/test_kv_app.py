import asyncio
import pytest


@pytest.mark.asyncio
async def test_vidhub_dropdown(kivy_app, KvEventWaiter):
    from vidhubcontrol.backends import DummyBackend

    kv_waiter = KvEventWaiter()

    config = kivy_app.vidhub_config
    dropdown = kivy_app.root.header_widget.vidhub_dropdown
    assert len(dropdown.btns) == 0

    kv_waiter.bind(dropdown, 'btns')
    vidhub1 = await DummyBackend.create_async(device_id='dummy1', device_name='Dummy 1')
    vidhub2 = await DummyBackend.create_async(device_id='dummy2', device_name='Dummy 2')
    await config.add_vidhub(vidhub1)
    await kv_waiter.wait()
    await config.add_vidhub(vidhub2)
    await kv_waiter.wait()
    kv_waiter.unbind(dropdown, 'btns')

    assert 'dummy1' in dropdown.btns
    assert 'dummy2' in dropdown.btns
    btn = dropdown.btns['dummy1']
    assert btn.device is vidhub1
    assert btn.text == vidhub1.device_name == 'Dummy 1'

    kv_waiter.bind(kivy_app, 'selected_device')
    btn.dispatch('on_release')
    await kv_waiter.wait()

    assert kivy_app.selected_device is vidhub1


    btn = dropdown.btns['dummy2']
    assert btn.device is vidhub2
    assert btn.text == vidhub2.device_name == 'Dummy 2'

    assert kv_waiter.empty()
    btn.dispatch('on_release')
    await kv_waiter.wait()
    assert kivy_app.selected_device is vidhub2
