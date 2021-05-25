import os
import asyncio
import time
import pytest

KIVY_STALL_TIMEOUT = 90

@pytest.fixture
async def kivy_app(tmpdir, monkeypatch):
    vidhub_conf = tmpdir.join('vidhubcontrol.json')
    ui_conf = tmpdir.join('vidhubcontrol-ui.ini')

    monkeypatch.setenv('KIVY_UNITTEST', '1')
    monkeypatch.setattr('vidhubcontrol.runserver.Config.DEFAULT_FILENAME', str(vidhub_conf))

    from vidhubcontrol.kivyui import main as kivy_main


    class AppOverride(kivy_main.VidhubControlApp):
        def __init__(self, **kwargs):
            kwargs['kv_file'] = os.path.join(kivy_main.APP_PATH, 'vidhubcontrol.kv')
            super().__init__(**kwargs)
            self._startup_ready = asyncio.Event()
            self._app_ready = asyncio.Event()

        def get_application_config(self):
            return str(ui_conf)

        async def start_async(self):
            """Use this method to start the app in tests
            """
            self._run_task = asyncio.ensure_future(self.async_run())
            await self.wait_for_widget_init()
            await self._app_ready.wait()

        async def stop_async(self):
            """Use this method to stop the app in tests
            """
            self.stop()
            await self._run_task

        def on_start(self, *args, **kwargs):
            super().on_start(*args, **kwargs)
            self._startup_ready.set()

        async def async_start(self):
            """Override of base class method to initialize config, interfaces, etc
            """
            await super().async_start()
            self._app_ready.set()

        async def wait_for_widget_init(self, root=None):
            await self._startup_ready.wait()
            if root is None:
                root = self.root
            def check_init():
                for w in root.walk():
                    if w.parent is None:
                        return False
                    if 'app' in w.properties() and w.app is None:
                        return False
                return True
            while not check_init():
                await asyncio.sleep(.01)

    app = AppOverride()
    await app.start_async()
    await wait_clock_frames(5)

    yield app

    await app.stop_async()

@pytest.fixture
def KvEventWaiter():
    class KvEventWaiter_(object):
        def __init__(self):
            self._loop = asyncio.get_event_loop()
            self.aio_event = asyncio.Event()
        def bind(self, obj, *events):
            kwargs = {e:self.kivy_callback for e in events}
            obj.bind(**kwargs)
        def unbind(self, obj, *events):
            kwargs = {e:self.kivy_callback for e in events}
            obj.unbind(**kwargs)
        async def wait(self, timeout=5):
            await asyncio.wait_for(self.aio_event.wait(), timeout)
            self.aio_event.clear()
        async def bind_and_wait(self, obj, timeout=5, *events):
            self.aio_event.clear()
            self.bind(obj, *events)
            await self.wait(timeout)
        def kivy_callback(self, *args, **kwargs):
            self.aio_event.set()

    return KvEventWaiter_
