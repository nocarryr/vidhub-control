#! /usr/bin/env python

import os
import signal
import asyncio
import argparse
import logging

from pid import PidFile

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
    for sig in [signal.SIGINT, signal.SIGTERM]:
        loop.add_signal_handler(sig, on_sigint, config, interfaces)
    logger.info('Ready')
    await config.stopped.wait()

def on_sigint(config, interfaces):
    logger.info('Exiting...')
    asyncio.ensure_future(stop(config, interfaces))

def main():
    with PidFile(pidname='vidhubcontrolserver.pid', force_tmpdir=True) as pf:
        opts = parse_args()
        loop = asyncio.get_event_loop()
        logger.info('Running server. Press CTRL+c to exit')
        loop.run_until_complete(run(loop, opts))

if __name__ == '__main__':
    main()
