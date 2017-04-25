import asyncio
import pytest

@pytest.mark.asyncio
async def test_vidhub_preset_edit(kivy_app, KvEventWaiter):
    kv_waiter = KvEventWaiter()
    kv_waiter.bind(kivy_app, 'on_start')
    kivy_app.run()
    await kv_waiter.wait()

    config = kivy_app.vidhub_config

    async def build_vidhub(**kwargs):
        async def do_build(**kwargs_):
            obj = config.build_backend('vidhub', 'DummyBackend', **kwargs_)
            await obj.connect_fut
        kivy_app.run_async_coro(do_build(**kwargs))

    kv_waiter.bind(kivy_app, 'vidhubs')

    await build_vidhub(device_id='dummy1', device_name='Dummy 1')
    await kv_waiter.wait()
    vidhub1 = kivy_app.vidhubs['dummy1']

    await build_vidhub(device_id='dummy2', device_name='Dummy 2')
    await kv_waiter.wait()
    vidhub2 = kivy_app.vidhubs['dummy2']

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = vidhub1
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')

    edit_widget = kivy_app.root.active_widget.vidhub_edit_widget
    preset_widget = edit_widget.preset_label_list

    async def open_selection_popup(xpt_widget_, selection_type):
        waiter = KvEventWaiter()
        waiter.bind(xpt_widget_, 'selection_popup')
        if selection_type == 'input':
            xpt_widget_.open_input_selection()
        else:
            xpt_widget_.open_output_selection()
        await waiter.wait()
        waiter.unbind(xpt_widget_, 'selection_popup')

        selection_popup = xpt_widget_.selection_popup
        if not selection_popup.button_grid.selections_loaded:
            waiter.bind(selection_popup.button_grid, 'selections_loaded')
            await waiter.wait()

        return selection_popup

    # Add empty preset

    kv_waiter.bind(preset_widget, 'list_items')
    preset_widget.add_preset()
    await kv_waiter.wait()

    preset_item_widget = preset_widget.list_items[0]
    kv_waiter.unbind(preset_widget, 'list_items')
    kv_waiter.bind(preset_item_widget, 'edit_popup_widget')
    preset_item_widget.open_edit_popup()
    await kv_waiter.wait()

    popup = preset_item_widget.edit_popup_widget
    kv_waiter.unbind(preset_item_widget, 'edit_popup_widget')
    await asyncio.sleep(.1)
    assert popup.preset == preset_item_widget.preset
    assert not len(popup.crosspoint_widgets)

    xpt_widget = popup.add_crosspoint()
    assert xpt_widget.dest == 0
    assert xpt_widget.source == 0
    assert xpt_widget.dest_label == vidhub1.output_labels[0]
    assert xpt_widget.source_label == vidhub1.input_labels[0]

    print('crosspoint_dict: ', popup.get_crosspoint_dict())


    # Set crosspoint source to 1

    xpt_popup = await open_selection_popup(xpt_widget, 'input')

    assert xpt_popup.button_grid.selected_output == xpt_widget.dest
    assert xpt_popup.button_grid.selected_buttons == [xpt_widget.source]

    kv_waiter.bind(xpt_popup.button_grid, 'selected_buttons')
    xpt_popup.button_grid.button_widgets[1].dispatch('on_release')
    await kv_waiter.wait()

    kv_waiter.unbind(xpt_popup.button_grid, 'selected_buttons')
    assert xpt_popup.button_grid.selected_buttons == [1]

    kv_waiter.bind(xpt_widget, 'selection_popup')
    xpt_popup.dispatch('on_submit')
    await kv_waiter.wait()

    kv_waiter.unbind(xpt_widget, 'selection_popup')
    assert xpt_widget.selection_popup is None
    assert xpt_widget.source == 1
    assert xpt_widget.source_label == vidhub1.input_labels[1]
    assert xpt_widget.preset.crosspoints.get(xpt_widget.dest) != xpt_widget.source

    print('crosspoint_dict: ', popup.get_crosspoint_dict())


    # Set crosspoint dest to 1

    xpt_popup = await open_selection_popup(xpt_widget, 'output')

    assert xpt_popup.button_grid.selected_input == xpt_widget.source
    assert xpt_popup.button_grid.selected_buttons == [xpt_widget.dest]

    kv_waiter.bind(xpt_popup.button_grid, 'selected_buttons')
    xpt_popup.button_grid.button_widgets[1].dispatch('on_release')
    await kv_waiter.wait()

    kv_waiter.unbind(xpt_popup.button_grid, 'selected_buttons')
    assert xpt_popup.button_grid.selected_buttons == [1]

    kv_waiter.bind(xpt_widget, 'selection_popup')
    xpt_popup.dispatch('on_submit')
    await kv_waiter.wait()

    kv_waiter.unbind(xpt_widget, 'selection_popup')
    assert xpt_widget.selection_popup is None
    assert xpt_widget.dest == 1
    assert xpt_widget.dest_label == vidhub1.output_labels[1]
    assert xpt_widget.preset.crosspoints.get(xpt_widget.dest) != xpt_widget.source

    print('crosspoint_dict: ', popup.get_crosspoint_dict())

    # Add new crosspoint.  Dest and Source should both be 0

    assert popup.next_available_dest() == 0

    xpt_widget = popup.add_crosspoint()
    await asyncio.sleep(.1)

    assert xpt_widget.source == 0
    assert xpt_widget.dest == 0
    assert xpt_widget.preset.crosspoints.get(xpt_widget.dest) != xpt_widget.source

    print('crosspoint_dict: ', popup.get_crosspoint_dict())


    # Add another crosspoint.  Dest and Source should both be 2

    assert popup.next_available_dest() == 2

    xpt_widget = popup.add_crosspoint(source=2)
    await asyncio.sleep(.1)

    assert xpt_widget.source == 2
    assert xpt_widget.dest == 2
    assert xpt_widget.preset.crosspoints.get(xpt_widget.dest) != xpt_widget.source

    print('crosspoint_dict: ', popup.get_crosspoint_dict())


    # Submit the edit and check the preset

    expected_xpts = {0:0, 1:1, 2:2}

    kv_waiter.bind(preset_item_widget, 'edit_popup_widget')
    popup.dispatch('on_submit')
    await kv_waiter.wait()

    assert preset_item_widget.preset.crosspoints == expected_xpts


    # Load the popup from the existing preset

    preset_item_widget.open_edit_popup()
    await kv_waiter.wait()

    popup = preset_item_widget.edit_popup_widget
    kv_waiter.unbind(preset_item_widget, 'edit_popup_widget')
    await asyncio.sleep(.1)

    assert popup.get_crosspoint_dict() == expected_xpts == preset_item_widget.preset.crosspoints

    await kivy_app.stop_async()
