import asyncio
import pytest

@pytest.mark.asyncio
async def test_vidhub_routing(kivy_app, KvEventWaiter):
    from vidhubcontrol.backends import SmartScopeDummyBackend

    kv_waiter = KvEventWaiter()
    kv_waiter.bind(kivy_app, 'on_start')
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config
    smartscope = await SmartScopeDummyBackend.create_async(device_name='Dummy 1')
    for monitor in smartscope.monitors:
        await monitor.set_property_from_backend('scope_mode', 'Picture')

    kv_waiter.bind(kivy_app, 'smartscopes')
    config.add_device(smartscope)
    await kv_waiter.wait()

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = smartscope
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')

    smartscope_widget = kivy_app.root.active_widget
    await kivy_app.wait_for_widget_init(smartscope_widget)


    while len(smartscope_widget.monitor_widget_container.children) < smartscope.num_monitors:
        await asyncio.sleep(0)

    def check_values():
        for monitor in smartscope.monitors:
            monitor_widget = smartscope_widget.monitor_widgets[monitor.index]

            assert monitor_widget.monitor is monitor
            assert monitor.name == monitor_widget.name

            # Numeric values
            for key in ['brightness', 'contrast', 'saturation', 'audio_channel']:
                assert getattr(monitor, key) == getattr(monitor_widget, key)

            # Choice values
            for key in ['widescreen_sd', 'scope_mode']:
                mon_val = monitor.get_choice_for_property(key, getattr(monitor, key))
                assert mon_val.lower() == getattr(monitor_widget, key).lower()

            assert monitor.identify == monitor_widget.identify

            assert str(monitor.border).lower() == monitor_widget.border.lower()

    check_values()

    # Set values from device
    for monitor in smartscope.monitors:
        props = monitor.PropertyChoices._bind_properties
        for prop in props:
            choices = monitor.get_property_choices(prop)
            if choices is not None:
                for prop_val, device_val in choices.items():
                    if getattr(monitor, prop) == prop_val:
                        continue
                    await monitor.set_property_from_backend(prop, device_val)
                    check_values()
            elif prop == 'identify':
                await monitor.set_property_from_backend(prop, str(not monitor.identify))
                check_values()
            else:
                for i in range(20):
                    await monitor.set_property_from_backend(prop, i)
                    check_values()

    await kivy_app.stop_async()
