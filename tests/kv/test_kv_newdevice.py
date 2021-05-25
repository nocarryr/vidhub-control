import asyncio
import pytest

@pytest.mark.asyncio
async def test_vidhub_routing(kivy_app, KvEventWaiter, mocked_vidhub_telnet_device):
    from vidhubcontrol.backends import DummyBackend

    kv_waiter = KvEventWaiter()

    config = kivy_app.vidhub_config

    def get_newdevice_btn(w):
        for _w in w.walk():
            if _w.__class__.__name__ != 'Button':
                continue
            if _w.text != 'Add New':
                continue
            return _w

    dropdown = kivy_app.root.header_widget.vidhub_dropdown
    btn = get_newdevice_btn(dropdown)

    kv_waiter.bind(kivy_app, 'popup_widget')
    btn.dispatch('on_release')
    await kv_waiter.wait()

    popup_widget = kivy_app.popup_widget

    assert popup_widget.port_widget.value == '9990'

    assert popup_widget.validate() is False
    assert popup_widget.ip_widget.validation_error is True
    assert popup_widget.ip_widget.validation_message == 'Required Field'

    popup_widget.ip_widget.value = '9'
    assert popup_widget.validate() is False
    assert popup_widget.ip_widget.validation_error is True
    assert popup_widget.ip_widget.validation_message == 'Invalid Address'

    popup_widget.ip_widget.value = '127.0.0.1'
    popup_widget.port_widget.value = ''
    assert popup_widget.validate() is False
    assert popup_widget.ip_widget.validation_error is False
    assert popup_widget.port_widget.validation_error is True
    assert popup_widget.port_widget.validation_message == 'Required Field'

    popup_widget.port_widget.value = 'baz'
    assert popup_widget.validate() is False
    assert popup_widget.ip_widget.validation_error is False
    assert popup_widget.port_widget.validation_error is True
    assert popup_widget.port_widget.validation_message == 'Integer Required'

    popup_widget.name_widget.value = 'foo'
    popup_widget.port_widget.value = '9990'

    assert popup_widget.validate() is True
    popup_widget.on_submit()

    await kv_waiter.wait()

    assert kivy_app.popup_widget is None

    await asyncio.sleep(.1)

    new_device = None
    for vidhub in config.vidhubs.values():
        if vidhub.device_name == 'foo':
            new_device = vidhub
            break
    assert new_device is not None
