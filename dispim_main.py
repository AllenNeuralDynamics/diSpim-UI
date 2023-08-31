"""Launch dispim UI"""

import os
from dispim_userinterface import UserInterface
import logging
from coloredlogs import ColoredFormatter
import sys
import ctypes
from datetime import datetime
from pathlib import Path
import napari

# Remove any handlers already attached to the root logger.
logging.getLogger().handlers.clear()

class SpimLogFilter(logging.Filter):
    # Note: calliphlox lib is quite chatty.
    VALID_LOGGER_BASES = {'spim_core', 'ispim', 'tigerasi' }

    def filter(self, record):
        return record.name.split('.')[0].lower() in \
               self.__class__.VALID_LOGGER_BASES



class create_UI():

    def __init__(self):
        simulated = False
        log_level = "DEBUG"  # ["INFO", "DEBUG"]
        color_console_output = True
        console_output = True

        # Setup logging.
        # Create log handlers to dispatch:
        # - User-specified level and above to print to console if specified.
        logger = logging.getLogger()  # get the root logger.
        # logger level must be set to the lowest level of any handler.
        logger.setLevel(logging.DEBUG)
        fmt = '%(asctime)s.%(msecs)03d %(levelname)s %(name)s: %(message)s'
        fmt = "[SIM] " + fmt if simulated else fmt
        datefmt = '%Y-%m-%d,%H:%M:%S'
        log_formatter = ColoredFormatter(fmt=fmt, datefmt=datefmt) \
            if color_console_output \
            else logging.Formatter(fmt=fmt, datefmt=datefmt)

        # Write logs to file to capture gui activity
        file_handler = logging.FileHandler(Path(f'./gui_log_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'), 'w')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(fmt=fmt, datefmt=datefmt))
        logger.addHandler(file_handler)
        # Print console output if user requests it
        if console_output:
            log_handler = logging.StreamHandler(sys.stdout)
            #log_handler.addFilter(SpimLogFilter())
            log_handler.setLevel(log_level)
            log_handler.setFormatter(log_formatter)
            logger.addHandler(log_handler)

        # Windows-based console needs to accept colored logs if running with color.
        if os.name == 'nt' and color_console_output:
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

        if simulated:
            config_path =  rf'C:\Users\{os.getlogin()}\Downloads\dispim_files\config.toml'
        else:
            config_path = rf'C:\Users\{os.getlogin()}\Documents\dispim_files\config.toml'


        self.UI = UserInterface(config_filepath=config_path,
                            console_output_level=log_level,
                            simulated=simulated)
        # finally:
        #     file_handler.close()
        #     logger.removeHandler(file_handler)

if __name__ == "__main__":
    run = create_UI()
    try:
        napari.run()
    finally:
        run.UI.close_instrument()