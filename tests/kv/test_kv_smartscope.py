import asyncio
import pytest

@pytest.mark.asyncio
async def test_kv_smartscope(kivy_app, KvEventWaiter):
    from vidhubcontrol.backends import SmartViewDummyBackend, SmartScopeDummyBackend
    from vidhubcontrol.common import ConnectionState

    kv_waiter = KvEventWaiter()

    config = kivy_app.vidhub_config
    smartscope = await SmartScopeDummyBackend.create_async(device_name='Scope 1')
    for monitor in smartscope.monitors:
        await monitor.set_property_from_backend('scope_mode', 'Picture')
    smartview = await SmartViewDummyBackend.create_async(device_name='Monitor 1')

    kv_waiter.bind(kivy_app, 'smartscopes')
    kv_waiter.bind(kivy_app, 'smartviews')
    await config.add_device(smartscope)
    await kv_waiter.wait()

    await config.add_device(smartview)
    await kv_waiter.wait()

    smartview_widget = None
    params = (
        ('smartview', smartview, 'smartviews'),
        ('smartscope', smartscope, 'smartscopes'),
    )
    for device_type, device, app_prop in params:
        kv_waiter = KvEventWaiter()

        if smartview_widget is None:
            kv_waiter.bind(kivy_app.root, 'active_widget')
            kivy_app.selected_device = device
            await kv_waiter.wait()
            kv_waiter.unbind(kivy_app.root, 'active_widget')
        else:
            kv_waiter.bind(smartview_widget, 'device')
            smartview_widget.device = None
            await kv_waiter.wait()
            kivy_app.selected_device = device
            while smartview_widget.device is not device:
                await kv_waiter.wait()
            kv_waiter.unbind(smartview_widget, 'device')
            await asyncio.sleep(.5)
            await kv_waiter.clear()

        smartview_widget = kivy_app.root.active_widget

        async def wait_for_monitor_init():
            await kivy_app.wait_for_widget_init(smartview_widget)

            while len(smartview_widget.monitor_widget_container.children) < device.num_monitors:
                await asyncio.sleep(0)

            async def wait_for_mon_widget(monitor_widget):
                await kivy_app.wait_for_widget_init(monitor_widget)
                while None in (monitor_widget.app, monitor_widget.monitor):
                    await asyncio.sleep(0)
                await asyncio.sleep(.2)

            coros = set()
            for monitor_widget in smartview_widget.monitor_widgets:
                coros.add(wait_for_mon_widget(monitor_widget))
            await asyncio.gather(*coros)

        await wait_for_monitor_init()

        def check_values():
            assert device.device_name == smartview_widget.name
            assert device.connection_state == smartview_widget.connection_state
            connected = device.connection_state == ConnectionState.connected
            assert smartview_widget.connected is connected

            for monitor in device.monitors:
                monitor_widget = smartview_widget.monitor_widgets[monitor.index]

                assert monitor_widget.monitor is monitor
                assert monitor.name == monitor_widget.name

                # Numeric values
                for key in ['brightness', 'contrast', 'saturation', 'audio_channel']:
                    assert getattr(monitor, key) == getattr(monitor_widget, key)

                # Choice values
                keys = ['widescreen_sd']
                if device_type == 'smartscope':
                    keys.append('scope_mode')
                for key in keys:
                    mon_val = monitor.get_choice_for_property(key, getattr(monitor, key))
                    assert mon_val.lower() == getattr(monitor_widget, key).lower()

                assert monitor.identify == monitor_widget.identify

                assert str(monitor.border).lower() == monitor_widget.border.lower()

        check_values()

        # Set values from device
        kv_waiter.bind(smartview_widget, 'name')
        device.device_name = 'FOO'
        await kv_waiter.wait()
        assert smartview_widget.name == 'FOO'

        kv_waiter.unbind(smartview_widget, 'name')

        print('set from backend')
        for monitor in device.monitors:
            print('monitor index: ', monitor.index)
            monitor_widget = smartview_widget.monitor_widgets[monitor.index]
            props = monitor.PropertyChoices._bind_properties
            for prop in props:
                print('prop: ', prop)
                kv_waiter.bind(monitor_widget, prop)
                choices = monitor.get_property_choices(prop)
                if choices is not None:
                    for prop_val, device_val in choices.items():
                        if getattr(monitor, prop) == prop_val:
                            continue
                        await monitor.set_property_from_backend(prop, device_val)
                        await kv_waiter.wait()
                        check_values()
                elif prop == 'identify':
                    await monitor.set_property_from_backend(prop, str(not monitor.identify))
                    await kv_waiter.wait()
                    check_values()
                else:
                    for i in range(20):
                        if getattr(monitor, prop) == i:
                            continue
                        await monitor.set_property_from_backend(prop, i)
                        await kv_waiter.wait()
                        check_values()
                kv_waiter.unbind(monitor_widget, prop)

        # Set values from ui
        def find_widget(monitor_widget, property_name):
            def find_root():
                for w in monitor_widget.walk():
                    if not hasattr(w, 'label_text'):
                        continue
                    if property_name == 'widescreen_sd' and w.label_text == 'WidescreenSD':
                        return w
                    if w.label_text.lower() == property_name:
                        return w
                    if '_'.join(w.label_text.split(' ')).lower() == property_name:
                        return w
            w = find_root()
            if w.__class__.__name__ == 'SliderSetting':
                clsname = 'Slider'
            elif w.__class__.__name__ == 'TextSetting':
                clsname = 'TextInput'
            elif w.__class__.__name__ == 'OptionSetting':
                clsname = 'Spinner'
            elif w.__class__.__name__ == 'BooleanSetting':
                clsname = 'Switch'
            for _w in w.walk():
                if _w.__class__.__name__ == clsname:
                    return _w


        async def set_monitor_prop_from_ui(monitor, monitor_widget, prop, value):
            widget = find_widget(monitor_widget, prop)

            if prop in ['brightness', 'contrast', 'saturation']:
                widget.value = value
            elif prop == 'border':
                widget.text = str(value).title()
            elif prop == 'identify':
                widget.active = value
            elif widget.__class__.__name__ == 'TextInput':
                widget.text = str(value)
                widget.dispatch('on_text_validate')
            else:
                widget.text = monitor.get_choice_for_property(prop, value).title()
            await asyncio.sleep(0)

        print('set from UI')
        for monitor, monitor_widget in zip(device.monitors, smartview_widget.monitor_widgets):
            print('monitor index: ', monitor.index)
            props = monitor.PropertyChoices._bind_properties
            for prop in props:
                print('prop: ', prop)
                kv_waiter.bind(monitor_widget, prop)
                choices = monitor.get_property_choices(prop)
                if choices is not None:
                    for prop_val, device_val in choices.items():
                        if getattr(monitor, prop) == prop_val:
                            continue
                        await set_monitor_prop_from_ui(monitor, monitor_widget, prop, prop_val)
                        await kv_waiter.wait()
                        check_values()
                elif prop == 'identify':
                    await set_monitor_prop_from_ui(monitor, monitor_widget, prop, not monitor.identify)
                    await kv_waiter.wait()
                    check_values()
                else:
                    for i in range(20):
                        if getattr(monitor, prop) == i:
                            continue
                        await set_monitor_prop_from_ui(monitor, monitor_widget, prop, i)
                        await kv_waiter.wait()
                        check_values()
                kv_waiter.unbind(monitor_widget, prop)

        # Test device_name edit
        smartview_widget.edit_name_enabled = True
        popup = kivy_app.popup_widget
        assert popup == smartview_widget.edit_name_widget
        assert popup.text == device.device_name

        new_name = f'{device_type}-foobar'
        popup.text = new_name
        popup.dispatch('on_cancel')

        assert kivy_app.popup_widget is None
        assert smartview_widget.edit_name_widget is None
        assert smartview_widget.edit_name_enabled is False
        assert device.device_name != new_name

        smartview_widget.edit_name_enabled = True
        popup = kivy_app.popup_widget
        assert popup == smartview_widget.edit_name_widget
        assert popup.text == device.device_name

        popup.text = new_name
        popup.dispatch('on_submit')

        assert device.device_name == new_name
        await kv_waiter.clear()
