import asyncio
import pytest

@pytest.mark.asyncio
async def test_vidhub_edit(kivy_app, KvEventWaiter):

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
    vidhub = kivy_app.vidhubs['dummy1']

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = vidhub
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')

    edit_widget = kivy_app.root.active_widget.vidhub_edit_widget

    list_widgets = {
        'input':edit_widget.input_label_list,
        'output':edit_widget.output_label_list,
        'preset':edit_widget.preset_label_list,
    }


    # Wait for widget creation

    def items_populated():
        if len(edit_widget.input_label_list.list_items) != vidhub.num_inputs:
            return False
        if len(edit_widget.output_label_list.list_items) != vidhub.num_outputs:
            return False
        if len(edit_widget.preset_label_list.list_items) != len(vidhub.presets):
            return False
        return True

    while not items_populated():
        await asyncio.sleep(0)



    def check_values():
        w = edit_widget.input_label_list
        for i, lbl in enumerate(vidhub.input_labels):
            item = w.list_items[i]
            assert item.text == lbl

        w = edit_widget.output_label_list
        for i, lbl in enumerate(vidhub.output_labels):
            item = w.list_items[i]
            assert item.text == lbl

        w = edit_widget.preset_label_list
        for preset in vidhub.presets:
            item = w.list_items[preset.index]
            assert item.preset is preset
            assert item.index == preset.index
            assert item.text == preset.name

    check_values()

    for lbl_type in ['input', 'output']:
        vidhub_labels = getattr(vidhub, '{}_labels'.format(lbl_type))
        vidhub_set_fn = getattr(vidhub, 'set_{}_label'.format(lbl_type))
        list_widget = getattr(edit_widget, '{}_label_list'.format(lbl_type))

        for i in range(len(vidhub_labels)):
            item = list_widget.list_items[i]
            kv_waiter.bind(item, 'text')

            # Set label from vidhub and test ui updates
            lbl = '{} FOO {}'.format(lbl_type, i)
            kivy_app.run_async_coro(vidhub_set_fn(i, lbl))
            await kv_waiter.wait()

            assert vidhub_labels[i] == item.text == lbl
            check_values()


            # Set label from TextInput and check vidhub updates
            txt_widget = None
            for w in item.children:
                if w.__class__.__name__ == 'TextInput':
                    txt_widget = w
                    break
            assert txt_widget is not None

            lbl = '{} BAR {}'.format(lbl_type, i)
            txt_widget.text = lbl
            txt_widget.dispatch('on_text_validate')
            await asyncio.sleep(0)
            await kv_waiter.wait()

            while vidhub_labels[i] != lbl:
                await asyncio.sleep(0)

            assert txt_widget.text == item.text == lbl
            check_values()

            kv_waiter.unbind(item, 'text')

    # Create presets so they can be edited
    for i in range(12):
        await vidhub.store_preset()

    while len(edit_widget.preset_label_list.list_items) != len(vidhub.presets):
        await asyncio.sleep(0)

    check_values()

    for preset in vidhub.presets:
        item = edit_widget.preset_label_list.list_items[preset.index]
        kv_waiter.bind(item, 'text')

        # Set label from vidhub and test ui updates
        lbl = 'Preset FOO {}'.format(preset.index)
        preset.name = lbl
        await kv_waiter.wait()
        assert item.text == preset.name == lbl
        check_values()


        # Set label from TextInput and check vidhub updates
        txt_widget = None
        for w in item.children:
            if w.__class__.__name__ == 'TextInput':
                txt_widget = w
                break
        assert txt_widget is not None

        lbl = 'Preset BAR {}'.format(preset.index)
        txt_widget.text = lbl
        txt_widget.dispatch('on_text_validate')
        await asyncio.sleep(0)
        await kv_waiter.wait()

        assert txt_widget.text == item.text == preset.name == lbl
        check_values()

        kv_waiter.unbind(item, 'text')

    # Set device_name
    txt_widget = edit_widget.device_name_text_widget
    kv_waiter.bind(edit_widget, 'text')
    txt_widget.text = 'foobar1'
    txt_widget.dispatch('on_text_validate')
    await asyncio.sleep(0)
    await kv_waiter.wait()

    assert txt_widget.text == edit_widget.text == vidhub.device_name == 'foobar1'

    await kivy_app.stop_async()
