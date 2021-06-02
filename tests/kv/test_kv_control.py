import asyncio
import pytest

@pytest.mark.asyncio
async def test_kv_control(kivy_app, KvEventWaiter):

    kv_waiter = KvEventWaiter()

    config = kivy_app.vidhub_config

    async def build_vidhub(**kwargs):
        async def do_build(**kwargs_):
            obj = await config.build_backend('vidhub', 'DummyBackend', **kwargs_)
            await obj.connect_fut
        return kivy_app.run_async_coro(do_build(**kwargs))

    kv_waiter.bind(kivy_app, 'vidhubs')

    await build_vidhub(device_id='dummy1', device_name='Dummy 1')
    await kv_waiter.wait()
    vidhub1 = kivy_app.vidhubs['dummy1']

    await build_vidhub(device_id='dummy2', device_name='Dummy 2')
    await kv_waiter.wait()
    vidhub2 = kivy_app.vidhubs['dummy2']

    kv_waiter.unbind(kivy_app, 'vidhubs')
    await kv_waiter.clear()

    kv_waiter.bind(kivy_app.root, 'active_widget')
    kivy_app.selected_device = vidhub1
    await kv_waiter.wait()
    kv_waiter.unbind(kivy_app.root, 'active_widget')
    await kv_waiter.clear()

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
            assert btn.title_text == lbl

            routed_dests = [out_idx for out_idx, in_idx in enumerate(_vidhub.crosspoints) if in_idx == i]
            assert btn.selected_outputs == routed_dests

            if not len(routed_dests):
                assert btn.content_text == ''
            elif len(routed_dests) == 1:
                assert btn.content_text == _vidhub.output_labels[routed_dests[0]]
            else:
                assert btn.content_text == ','.join([str(out_idx) for out_idx in routed_dests])

            if i in input_states:
                assert btn.selection_state == input_states[i]
            else:
                assert btn.selection_state == 'normal'

        for i in range(_vidhub.num_outputs):
            lbl = _vidhub.output_labels[i]
            assert output_button_grid.button_labels[i] == lbl

            btn = output_button_grid.button_widgets[i]
            assert btn.title_text == lbl

            selected_input = _vidhub.crosspoints[i]
            assert btn.selected_input == selected_input
            assert btn.content_text == _vidhub.input_labels[selected_input]

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
    kivy_app.run_async_coro(vidhub1.set_input_labels(*lbls))

    lbls = [(i, 'FOO OUT {}'.format(i)) for i in range(vidhub1.num_outputs)]
    kivy_app.run_async_coro(vidhub1.set_output_labels(*lbls))

    await kv_waiter.wait()
    await kv_waiter2.wait()
    check_values(vidhub1)

    kv_waiter.unbind(input_button_grid, 'button_labels')
    kv_waiter2.unbind(output_button_grid, 'button_labels')
    await asyncio.sleep(.5)
    await kv_waiter.clear()
    await kv_waiter2.clear()

    kv_waiter.bind(input_button_grid, 'selected_buttons')
    kv_waiter2.bind(output_button_grid, 'selected_buttons')

    print('testing output-first routing')
    for out_idx in range(vidhub1.num_outputs):
        expected_input_btn = vidhub1.crosspoints[out_idx]
        should_change = input_button_grid.selected_buttons != [expected_input_btn]

        output_button_grid.button_widgets[out_idx].dispatch('on_release')
        await kv_waiter2.wait()
        assert output_button_grid.selected_buttons == [out_idx]
        if should_change:
            await kv_waiter.wait()
            assert input_button_grid.selected_buttons == [expected_input_btn]
        else:
            await asyncio.sleep(.1)
            assert kv_waiter.empty()
            assert kv_waiter2.empty()

        check_values(vidhub1)

        for in_idx in range(vidhub1.num_inputs):
            if vidhub1.crosspoints[out_idx] == in_idx:
                src = in_idx + 1
                if src >= vidhub1.num_inputs:
                    src = 0
            else:
                src = in_idx
            if vidhub1.crosspoints[out_idx] == src:
                assert input_button_grid.selected_buttons == [src]
                continue

            print('out {} -> in {}'.format(out_idx, src))
            input_button_grid.button_widgets[src].dispatch('on_release')
            await kv_waiter.wait()
            check_values(vidhub1)

        # Output already selected, deselect
        output_button_grid.button_widgets[out_idx].dispatch('on_release')
        await kv_waiter.wait()
        assert input_button_grid.selected_buttons == []
        await kv_waiter2.wait()
        assert output_button_grid.selected_buttons == []
        assert vidhub_widget.first_selected == 'None'
        check_values(vidhub1)

    await asyncio.sleep(.5)
    assert kv_waiter.empty()
    assert kv_waiter2.empty()

    print('testing input-first routing')
    for in_idx in range(vidhub1.num_inputs):
        expected_output_btns = set([_i for _i, _j in enumerate(vidhub1.crosspoints) if _j == in_idx])
        should_change = output_button_grid.selected_buttons == expected_output_btns

        input_button_grid.button_widgets[in_idx].dispatch('on_release')
        arg1, _ = await kv_waiter.wait()
        _, val = arg1
        assert val == [in_idx]
        if should_change:
            arg2, _ = await kv_waiter2.wait()
            _, val = arg2
            assert set(val) == expected_output_btns
        else:
            await asyncio.sleep(.1)
            assert kv_waiter.empty()
            if not kv_waiter2.empty():
                arg2, _ = await kv_waiter2.wait()
                _, val = arg2
                assert set(val) == expected_output_btns
            assert set(output_button_grid.selected_buttons) == expected_output_btns

        check_values(vidhub1)

        for out_idx in range(vidhub1.num_outputs):
            if vidhub1.crosspoints[out_idx] == in_idx:
                dest = out_idx + 1
                if dest >= vidhub1.num_outputs:
                    dest = 0
            else:
                dest = out_idx

            if vidhub1.crosspoints[dest] == in_idx:
                await asyncio.sleep(.1)
                assert kv_waiter.empty()
                assert kv_waiter2.empty()
                assert set(output_button_grid.selected_buttons) == expected_output_btns
                continue

            assert dest not in expected_output_btns
            expected_output_btns.add(dest)

            print('out {} -> in {}'.format(dest, in_idx))
            output_button_grid.button_widgets[dest].dispatch('on_release')
            await kv_waiter2.wait()
            assert set(output_button_grid.selected_buttons) == expected_output_btns
            while vidhub1.crosspoints[dest] != in_idx:
                await asyncio.sleep(0)
            await asyncio.sleep(0.01)
            check_values(vidhub1)

        # Output already selected, deselect
        inp_should_change = input_button_grid.selected_buttons != []
        out_should_change = output_button_grid.selected_buttons != []

        print(f'inp.btn{in_idx}.on_release')
        input_button_grid.button_widgets[in_idx].dispatch('on_release')
        await kv_waiter.wait()
        assert input_button_grid.selected_buttons == []
        await kv_waiter2.wait()
        assert output_button_grid.selected_buttons == []
        assert vidhub_widget.first_selected == 'None'
        check_values(vidhub1)

    await kv_waiter.clear()
    await kv_waiter2.clear()

    print('testing crosspoint changes from vidhub backend')
    vidhub1.crosspoints[:] = [2]*vidhub1.num_inputs
    for i in range(vidhub1.num_inputs):
        input_button_grid.button_widgets[i].dispatch('on_release')
        await kv_waiter.wait()
        xpts = [(i, i)] * vidhub1.num_outputs
        print(xpts)
        await vidhub1.set_crosspoints(*xpts)
        await kv_waiter2.wait()
        await asyncio.sleep(.1)
        check_values(vidhub1)
