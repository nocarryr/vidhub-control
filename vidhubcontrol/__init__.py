import os
import sys

def get_is_kivy_run():
    if os.environ.get('VIDHUBCONTROL_USE_KIVY') == '1':
        return True
    for arg in sys.argv:
        if 'vidhubcontrol-ui' in arg:
            return True
    return False
IS_KIVY_RUN = get_is_kivy_run()

from loguru import logger
import logging

level_per_module = {
    '': 'INFO',
    'vidhubcontrol': 'DEBUG',
    'vidhubcontrol.backends': 'INFO',
}
logger.remove(0)
logger.add(sys.stderr, filter=level_per_module)

orig_stderr = sys.stderr
root_logger = logging.getLogger()
logger.info(f'{root_logger=}, {orig_stderr=}, {logger=}')

if IS_KIVY_RUN:
    os.environ['KIVY_NO_CONSOLELOG'] = '1'
    logger.info(f'reclaiming logger: root={root_logger}')
    class InterceptHandler(logging.Handler):
        def emit(self, record):
            try:
                level = logger.level(record.levelname).name
            except ValueError:
                level = record.levelno
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1
            logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

    import kivy.logger
    kivy.logger.Logger.addHandler(InterceptHandler())

    logging.root = root_logger
    sys.stderr = orig_stderr
