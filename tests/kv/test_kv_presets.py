import asyncio
import pytest

@pytest.mark.asyncio
async def test_vidhub_routing(kivy_app, KvEventWaiter):
    from vidhubcontrol.backends import DummyBackend

    kv_waiter = KvEventWaiter()
    kv_waiter.bind(kivy_app, 'on_start')
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config
    vidhub = await DummyBackend.create_async(device_id='dummy1', device_name='Dummy 1')

    kv_waiter.bind(kivy_app, 'vidhubs')
    config.add_vidhub(vidhub)
    await kv_waiter.wait()

    vidhub_widget = kivy_app.root.vidhub_widget
    input_button_grid = vidhub_widget.input_button_grid
    output_button_grid = vidhub_widget.output_button_grid
    preset_button_grid = vidhub_widget.preset_button_grid

    kv_waiter.bind(vidhub_widget, 'vidhub')
    kivy_app.selected_vidhub = vidhub
    await kv_waiter.wait()

    await kivy_app.wait_for_widget_init(vidhub_widget)

    store_btn = None
    for w in preset_button_grid.walk():
        if w.__class__.__name__ != 'Button':
            continue
        if w.text == 'Store':
            store_btn = w
            break
    assert store_btn is not None

    kv_waiter.bind(preset_button_grid, 'record_enable')
    store_btn.dispatch('on_release')
    await kv_waiter.wait()

    assert preset_button_grid.record_enable is True
    assert store_btn.state == 'down'

    kv_waiter.unbind(preset_button_grid, 'record_enable')
    kv_waiter.bind(preset_button_grid, 'selected_buttons')

    xpts1 = [0] * vidhub.num_outputs
    await vidhub.set_crosspoints(*((i, v) for i, v in enumerate(xpts1)))

    # Store to preset index 0
    preset_button_grid.button_widgets[0].dispatch('on_release')
    await kv_waiter.wait()

    preset1 = vidhub.presets[0]

    assert preset_button_grid.record_enable is False
    assert len(preset_button_grid.selected_buttons) == 1
    assert preset_button_grid.selected_buttons[0] == preset1.index
    assert preset_button_grid.button_widgets[preset1.index].text == preset1.name

    # Set crosspoints - preset 0 should be inactive
    xpts2 = [1] * vidhub.num_outputs
    await vidhub.set_crosspoints(*((i, v) for i, v in enumerate(xpts2)))
    await kv_waiter.wait()

    assert len(preset_button_grid.selected_buttons) == 0

    # Store to preset index 1
    store_btn.dispatch('on_release')
    await asyncio.sleep(0)
    preset_button_grid.button_widgets[1].dispatch('on_release')
    await kv_waiter.wait()

    preset2 = vidhub.presets[1]

    assert len(preset_button_grid.selected_buttons) == 1
    assert preset_button_grid.selected_buttons[0] == preset2.index
    assert preset_button_grid.button_widgets[preset2.index].text == preset2.name

    # Recall preset index 0

    preset_button_grid.button_widgets[0].dispatch('on_release')
    await kv_waiter.wait()
    # Allow time for all events to dispatch
    if len(preset_button_grid.selected_buttons) == 0:
        await kv_waiter.wait()

    assert len(preset_button_grid.selected_buttons) == 1
    assert preset_button_grid.selected_buttons[0] == preset1.index

    # Test preset name binding
    kv_waiter.bind(preset_button_grid.button_widgets[0], 'text')

    preset1.name = 'foo'
    await kv_waiter.wait()

    assert preset_button_grid.button_widgets[0].text == preset1.name
    assert preset_button_grid.button_labels[0] == preset1.name


    await kivy_app.stop_async()
