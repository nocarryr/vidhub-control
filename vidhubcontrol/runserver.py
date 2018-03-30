#! /usr/bin/env python

import os
import sys
import tempfile
import signal
import asyncio
import argparse
import logging
from functools import partial

from pidfile import PIDFile

if sys.platform == 'win32':
    PIDPATH = os.path.join(os.environ['APPDATA'], 'vidhubcontrol')
    if not os.path.exists(PIDPATH):
        os.makedirs(PIDPATH)
else:
    PIDPATH = tempfile.gettempdir()
PID_FILENAME = os.path.join(PIDPATH, 'vidhubcontrol-server.pid')

class PIDFileWrapper(PIDFile):
    @property
    def filename(self):
        return self._PIDFile__file
    @property
    def checked(self):
        return self._PIDFile__checked
    @checked.setter
    def checked(self, value):
        self._PIDFile__checked = value
    def __enter__(self):
        super().__enter__()
        self.checked = True
        return self
    def __exit__(self, *args):
        super().__exit__(*args)
        if self.checked and os.path.exists(self.filename):
            os.unlink(self.filename)


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s\t%(name)s\t%(levelname)s\t%(message)s',
)

if __name__ == '__main__':
    logger = logging.getLogger('runserver')
else:
    logger = logging.getLogger(__name__)

from vidhubcontrol.config import Config
from vidhubcontrol.interfaces.osc import OscInterface

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('-c', '--config', dest='config_filename',
        default=Config.DEFAULT_FILENAME, help='Configuration filename')
    p.add_argument('--osc-address', dest='osc_address',
        help='Host address for OSC server. If not specified, one will be detected.')
    p.add_argument('--osc-port', dest='osc_port', default=OscInterface.DEFAULT_HOSTPORT,
        type=int, help='Host port for OSC server')
    p.add_argument('--osc-if-name', dest='osc_iface_name',
        help='Name of network interface to use for OSC server. If not specified, one will be detected.')
    p.add_argument('--osc-disabled', dest='osc_disabled', action='store_true',
        help='Disable OSC server')
    return p.parse_args()

async def start(loop, opts):
    Config.loop = loop
    config = await Config.load_async(opts.config_filename)
    await config.start()
    logger.debug('Config started')
    interfaces = []
    if not opts.osc_disabled:
        logger.debug('Building OSC')
        osc = OscInterface(
            config=config,
            hostaddr=opts.osc_address,
            hostport=opts.osc_port,
            hostiface=opts.osc_iface_name,
            event_loop=loop,
        )
        logger.debug('OSC built')
        await osc.start()
        logger.debug('OSC Started')
        interfaces.append(osc)
    return config, interfaces

async def stop(config, interfaces):
    logger.debug('Stopping interfaces')
    for obj in interfaces:
        await obj.stop()
    logger.debug('Stopping config')
    await config.stop()

async def run(loop, opts):
    config, interfaces = await start(loop, opts)
    if sys.platform == 'win32':
        async def wakeup():
            try:
                while config.running.is_set():
                    await asyncio.sleep(.1)
            except KeyboardInterrupt:
                await stop(config, interfaces)
            await config.stopped.wait()
        logger.info('ready')
        await wakeup()
    else:
        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(sig, on_sigint, config, interfaces)
        logger.info('Ready')
        await config.stopped.wait()

def on_sigint(config, interfaces):
    logger.info('Exiting...')
    asyncio.ensure_future(stop(config, interfaces))

def main():
    with PIDFileWrapper(PID_FILENAME):
        opts = parse_args()
        loop = asyncio.get_event_loop()
        logger.info('Running server. Press CTRL+c to exit')
        loop.run_until_complete(run(loop, opts))

if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except RuntimeError as e:
        if 'program already running' in str(e).lower():
            print('vidhub-control server already running')
            # EX_OSERR        71      /* system error (e.g., can't fork) */
            sys.exit(71)
        else:
            raise
