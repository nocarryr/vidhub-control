import asyncio
import pytest

@pytest.mark.asyncio
async def test_numeric_widget(kivy_app, KvEventWaiter):
    from vidhubcontrol.backends import SmartViewDummyBackend

    kv_waiter = KvEventWaiter()
    kv_waiter.bind(kivy_app, 'on_start')
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config

    smartview = await SmartViewDummyBackend.create_async(device_name='Dummy 1')

    kv_waiter.bind(kivy_app, 'smartviews')

    await config.add_device(smartview)
    await kv_waiter.wait()

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = smartview
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')

    smartview_widget = kivy_app.root.active_widget
    await kivy_app.wait_for_widget_init(smartview_widget)

    while len(smartview_widget.monitor_widget_container.children) < smartview.num_monitors:
        await asyncio.sleep(0)
    await asyncio.sleep(.1)

    def find_widget(monitor_widget, property_name):
        for w in monitor_widget.walk():
            if not hasattr(w, 'label_text'):
                continue
            if w.label_text.lower() == property_name:
                return w

    async def set_monitor_prop_from_ui(monitor, monitor_widget, prop, value):
        widget = find_widget(monitor_widget, prop)
        widget.set_value(value)
        await asyncio.sleep(0)

    async def simulate_button_hold(btn_widget, duration):
        _loop = asyncio.get_event_loop()
        assert btn_widget.state == 'normal'
        press_ts = _loop.time()
        kv_waiter.bind(btn_widget, 'on_release')
        btn_widget.trigger_action(duration)
        await kv_waiter.wait()
        release_ts = _loop.time()
        real_duration = release_ts - press_ts
        kv_waiter.unbind(btn_widget, 'on_release')
        return real_duration

    # Test inc/dec functions in NumericSetting
    queue_waiter = KvEventWaiter(use_queue=True)
    monitor = smartview.monitors[0]
    monitor_widget = smartview_widget.monitor_widgets[0]
    prop = 'brightness'
    queue_waiter.bind(monitor_widget, prop)
    widget = find_widget(monitor_widget, prop)
    inc_btn = widget.ids.inc_btn
    dec_btn = widget.ids.dec_btn

    # Check bounds
    await set_monitor_prop_from_ui(monitor, monitor_widget, prop, 1)
    await queue_waiter.wait()
    assert widget.value == 1
    await simulate_button_hold(dec_btn, dec_btn.repeat_delay + .5)
    await queue_waiter.wait()
    assert queue_waiter.queue.qsize() == 0
    assert widget.value == 0

    await set_monitor_prop_from_ui(monitor, monitor_widget, prop, 254)
    await queue_waiter.wait()
    assert widget.value == 254
    await simulate_button_hold(inc_btn, inc_btn.repeat_delay + .5)
    await queue_waiter.wait()
    assert queue_waiter.queue.qsize() == 0
    assert widget.value == 255

    # Check hold/repeat
    current_value = 127
    await set_monitor_prop_from_ui(monitor, monitor_widget, prop, current_value)
    await queue_waiter.wait()
    assert widget.value == current_value
    expected_value = 180
    num_repeats = expected_value - current_value
    hold_duration = inc_btn.repeat_interval * num_repeats + inc_btn.repeat_delay

    print('simulating button hold for {} seconds'.format(hold_duration))
    real_duration = await simulate_button_hold(inc_btn, hold_duration)
    print('button held for {} seconds'.format(real_duration))

    await queue_waiter.wait_for_all()
    print('expected_value={}, widget.value={}'.format(expected_value, widget.value))
    assert abs(expected_value - widget.value) <= 3


    current_value = widget.value
    num_repeats = 20
    expected_value = current_value - num_repeats
    hold_duration = dec_btn.repeat_interval * num_repeats + dec_btn.repeat_delay

    print('simulating button hold for {} seconds'.format(hold_duration))
    real_duration = await simulate_button_hold(dec_btn, hold_duration)
    print('button held for {} seconds'.format(real_duration))

    await queue_waiter.wait_for_all()
    print('expected_value={}, widget.value={}'.format(expected_value, widget.value))
    assert abs(expected_value - widget.value) <= 3

    queue_waiter.unbind(monitor_widget, prop)

    await kivy_app.stop_async()
