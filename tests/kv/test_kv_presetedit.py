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

    async def open_edit_popup(preset_index):
        waiter = KvEventWaiter()
        _preset_item_widget = preset_widget.list_items[preset_index]
        waiter.bind(_preset_item_widget, 'edit_popup_widget')
        _preset_item_widget.open_edit_popup()
        await waiter.wait()
        _popup = _preset_item_widget.edit_popup_widget
        waiter.unbind(_preset_item_widget, 'edit_popup_widget')
        await asyncio.sleep(.1)
        return _preset_item_widget, _popup

    async def close_edit_popup(_popup, submit=False):
        waiter = KvEventWaiter()
        _preset_item_widget = preset_widget.list_items[_popup.preset.index]
        waiter.bind(_preset_item_widget, 'edit_popup_widget')
        if submit:
            _popup.dispatch('on_submit')
        else:
            _popup.dispatch('on_cancel')
        await waiter.wait()
        waiter.unbind(_preset_item_widget, 'edit_popup_widget')

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

    preset_item_widget, popup = await open_edit_popup(0)
    kv_waiter.unbind(preset_widget, 'list_items')

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

    await close_edit_popup(popup, submit=True)

    assert preset_item_widget.preset.crosspoints == expected_xpts


    # Load the popup from the existing preset

    preset_index = preset_item_widget.preset.index
    preset_item_widget, popup = await open_edit_popup(preset_index)

    print('crosspoint_dict: ', popup.get_crosspoint_dict())
    assert popup.get_crosspoint_dict() == expected_xpts == preset_item_widget.preset.crosspoints

    await close_edit_popup(popup)


    # Store new preset from main page using "1 to 1" routing
    await vidhub1.set_crosspoints(*((i, i) for i in range(vidhub1.num_outputs)))

    preset_button_grid = kivy_app.root.active_widget.vidhub_widget.preset_button_grid

    kv_waiter.bind(preset_button_grid, 'selected_buttons')
    preset = await vidhub1.store_preset()
    await kv_waiter.wait()
    kv_waiter.unbind(preset_button_grid, 'selected_buttons')

    preset_item_widget, popup = await open_edit_popup(preset.index)
    print('crosspoint_dict: ', popup.get_crosspoint_dict())

    preset_xpts = preset.crosspoints.copy()

    assert popup.preset == preset_item_widget.preset == preset
    assert len(popup.crosspoint_widgets) == len(preset_xpts) == vidhub1.num_outputs
    assert popup.get_crosspoint_dict() == preset_xpts


    # Remove crosspoint, check values, then cancel

    kv_waiter.bind(popup, 'crosspoint_widgets')
    popup.crosspoint_widgets[0].dispatch('on_crosspoint_remove', widget=popup.crosspoint_widgets[0])
    await kv_waiter.wait()
    kv_waiter.unbind(popup, 'crosspoint_widgets')
    print('crosspoint_dict: ', popup.get_crosspoint_dict())

    assert popup.get_crosspoint_dict() != preset.crosspoints
    assert len(popup.get_crosspoint_dict()) == len(preset.crosspoints)-1
    assert 0 not in popup.get_crosspoint_dict()

    await close_edit_popup(popup)

    assert preset.crosspoints == preset_xpts

    # Remove crosspoint, submit changes, then check values
    preset_item_widget, popup = await open_edit_popup(preset.index)
    assert popup.get_crosspoint_dict() == preset_xpts

    kv_waiter.bind(popup, 'crosspoint_widgets')
    popup.crosspoint_widgets[0].dispatch('on_crosspoint_remove', widget=popup.crosspoint_widgets[0])
    await kv_waiter.wait()
    kv_waiter.unbind(popup, 'crosspoint_widgets')
    print('crosspoint_dict: ', popup.get_crosspoint_dict())

    expected_xpts = popup.get_crosspoint_dict()

    await close_edit_popup(popup, submit=True)

    assert preset.crosspoints != preset_xpts
    assert preset.crosspoints == expected_xpts
    assert 0 not in preset.crosspoints


    # Add the previously removed crosspoint (input 0 -> output 0)

    preset_xpts = preset.crosspoints.copy()
    expected_xpts = preset.crosspoints.copy()
    expected_xpts[0] = 0

    preset_item_widget, popup = await open_edit_popup(preset.index)
    assert popup.get_crosspoint_dict() == preset_xpts
    assert popup.next_available_dest() == 0

    xpt_widget = popup.add_crosspoint(source=0)
    await asyncio.sleep(.1)
    print('crosspoint_dict: ', popup.get_crosspoint_dict())

    assert xpt_widget.source == 0
    assert xpt_widget.dest == 0
    assert xpt_widget.preset.crosspoints.get(xpt_widget.dest) != xpt_widget.source
    assert popup.get_crosspoint_dict() == expected_xpts

    await close_edit_popup(popup, submit=True)

    assert preset.crosspoints == expected_xpts


    # Set first xpt widget dest from 0 to 1.
    # The existing widget with dest == 0 should be removed

    preset_xpts = preset.crosspoints.copy()
    expected_xpts = preset.crosspoints.copy()
    del expected_xpts[0]
    expected_xpts[1] = 0

    preset_item_widget, popup = await open_edit_popup(preset.index)
    assert popup.get_crosspoint_dict() == preset_xpts
    assert popup.next_available_dest() is None

    xpt_widget = popup.crosspoint_widgets[0]
    old_xpt_widget = popup.crosspoint_widgets[1]
    xpt_popup = await open_selection_popup(xpt_widget, 'output')

    kv_waiter.bind(xpt_popup.button_grid, 'selected_buttons')
    xpt_popup.button_grid.button_widgets[1].dispatch('on_release')
    await kv_waiter.wait()

    kv_waiter.unbind(xpt_popup.button_grid, 'selected_buttons')
    assert xpt_popup.button_grid.selected_buttons == [1]

    kv_waiter.bind(xpt_widget, 'selection_popup')
    xpt_popup.dispatch('on_submit')
    await kv_waiter.wait()
    kv_waiter.unbind(xpt_widget, 'selection_popup')

    await asyncio.sleep(.1)

    print('crosspoint_dict: ', popup.get_crosspoint_dict())
    assert old_xpt_widget not in popup.crosspoint_widgets.values()
    assert popup.crosspoint_widgets[1] == xpt_widget
    assert 0 not in popup.crosspoint_widgets
    assert popup.get_crosspoint_dict() == expected_xpts

    await close_edit_popup(popup, submit=True)

    assert preset.crosspoints == expected_xpts

    await kivy_app.stop_async()
