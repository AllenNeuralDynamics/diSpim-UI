"""Script to launch UI"""
import os
from dispim_userinterface import UserInterface
import traceback

if __name__ == '__main__':

    simulated = False
    log_level = "INFO"      # ["INFO", "DEBUG"]

    if simulated:
        config_path =  rf'C:\Users\{os.getlogin()}\Downloads\dispim_files\config.toml'
    else:
        config_path = rf'C:\Users\{os.getlogin()}\Documents\dispim_files\config.toml'

    run = UserInterface(config_filepath=config_path,
                        console_output_level=log_level,
                        simulated=simulated)
