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
    vidhub1 = await DummyBackend.create_async(device_id='dummy1', device_name='Dummy 1')
    vidhub2 = await DummyBackend.create_async(device_id='dummy2', device_name='Dummy 2')

    kv_waiter.bind(kivy_app, 'vidhubs')
    config.add_vidhub(vidhub1)
    await kv_waiter.wait()
    config.add_vidhub(vidhub2)
    await kv_waiter.wait()

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = vidhub1
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')

    vidhub_widget = kivy_app.root.active_widget.vidhub_widget
    input_button_grid = vidhub_widget.input_button_grid
    output_button_grid = vidhub_widget.output_button_grid

    assert vidhub_widget.vidhub is vidhub1

    await kivy_app.wait_for_widget_init(vidhub_widget)

    assert len(input_button_grid.children) == vidhub1.num_inputs
    assert len(output_button_grid.children) == vidhub1.num_outputs

    def check_values(_vidhub):
        if vidhub_widget.first_selected == 'output':
            selected_output = output_button_grid.selected_buttons[0]
            output_states = {selected_output:'flash'}
            input_states = {_vidhub.crosspoints[selected_output]:'down'}
        elif vidhub_widget.first_selected == 'input':
            selected_input = input_button_grid.selected_buttons[0]
            input_states = {selected_input:'flash'}
            output_states = {out_idx:'down' for out_idx, in_idx in enumerate(_vidhub.crosspoints) if in_idx == selected_input}
        else:
            input_states = {}
            output_states = {}

        for i in range(_vidhub.num_inputs):
            lbl = _vidhub.input_labels[i]
            assert input_button_grid.button_labels[i] == lbl

            btn = input_button_grid.button_widgets[i]
            assert btn.text == lbl
            if i in input_states:
                assert btn.selection_state == input_states[i]
            else:
                assert btn.selection_state == 'normal'
        for i in range(_vidhub.num_outputs):
            lbl = _vidhub.output_labels[i]
            assert output_button_grid.button_labels[i] == lbl

            btn = output_button_grid.button_widgets[i]
            assert btn.text == lbl
            if i in output_states:
                assert btn.selection_state == output_states[i]
            else:
                assert btn.selection_state == 'normal'

    check_values(vidhub1)

    print('testing label updates')
    kv_waiter2 = KvEventWaiter()

    kv_waiter.bind(input_button_grid, 'button_labels')
    kv_waiter2.bind(output_button_grid, 'button_labels')

    lbls = [(i, 'FOO IN {}'.format(i)) for i in range(vidhub1.num_inputs)]
    await vidhub1.set_input_labels(*lbls)

    lbls = [(i, 'FOO OUT {}'.format(i)) for i in range(vidhub1.num_outputs)]
    await vidhub1.set_output_labels(*lbls)

    await kv_waiter.wait()
    await kv_waiter2.wait()
    check_values(vidhub1)

    kv_waiter.unbind(input_button_grid, 'button_labels')
    kv_waiter2.unbind(output_button_grid, 'button_labels')

    kv_waiter.bind(input_button_grid, 'selected_buttons')
    kv_waiter2.bind(output_button_grid, 'selected_buttons')

    print('testing output-first routing')
    for out_idx in range(vidhub1.num_outputs):
        output_button_grid.button_widgets[out_idx].dispatch('on_release')
        await kv_waiter.wait()
        await kv_waiter2.wait()
        check_values(vidhub1)
        for in_idx in range(vidhub1.num_inputs):
            if vidhub1.crosspoints[out_idx] == in_idx:
                src = in_idx + 1
                if src >= vidhub1.num_inputs:
                    src = 0
            else:
                src = in_idx
            print('out {} -> in {}'.format(out_idx, src))
            input_button_grid.button_widgets[src].dispatch('on_release')
            await kv_waiter.wait()
            check_values(vidhub1)

        # Output already selected, deselect
        output_button_grid.button_widgets[out_idx].dispatch('on_release')
        await kv_waiter.wait()
        await kv_waiter2.wait()
        assert vidhub_widget.first_selected == 'None'
        check_values(vidhub1)

    print('testing input-first routing')
    for in_idx in range(vidhub1.num_inputs):
        input_button_grid.button_widgets[in_idx].dispatch('on_release')
        await kv_waiter.wait()
        await kv_waiter2.wait()
        check_values(vidhub1)
        for out_idx in range(vidhub1.num_outputs):
            if vidhub1.crosspoints[out_idx] == in_idx:
                dest = vidhub1.crosspoints[out_idx] + 1
                if dest >= vidhub1.num_outputs:
                    dest = 0
            else:
                dest = in_idx

            print('out {} -> in {}'.format(dest, in_idx))
            output_button_grid.button_widgets[dest].dispatch('on_release')
            while vidhub1.crosspoints[dest] != in_idx:
                await asyncio.sleep(0)
            check_values(vidhub1)

        # Output already selected, deselect
        input_button_grid.button_widgets[in_idx].dispatch('on_release')
        await kv_waiter.wait()
        await kv_waiter2.wait()
        assert vidhub_widget.first_selected == 'None'
        check_values(vidhub1)

    print('testing crosspoint changes from vidhub backend')
    vidhub1.crosspoints[:] = [2]*vidhub1.num_inputs
    for i in range(vidhub1.num_inputs):
        input_button_grid.button_widgets[i].dispatch('on_release')
        await kv_waiter.wait()
        xpts = [(i, i)] * vidhub1.num_outputs
        print(xpts)
        await vidhub1.set_crosspoints(*xpts)
        await kv_waiter2.wait()
        check_values(vidhub1)


    await kivy_app.stop_async()
