import argparse
import os
from dispim_userinterface import UserInterface
import traceback

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--config_path", type=str, default=None)
    parser.add_argument("--log_level", type=str, default="DEBUG",
                        choices=["INFO", "DEBUG"])
    parser.add_argument("--simulated", default=False, action="store_true",
                        help="Simulate hardware device connections.")
    # Note: colored console output is buggy on Windows.
    parser.add_argument("--color_console_output", type=bool,
                        default=False if os.name == 'nt' else True)

    args = parser.parse_args()
    # Check if we didn't supply a config file and populate a safe guess.
    if not args.config_path:
        if args.simulated:
            args.config_path = r'C:\Users\micah.woodard\dispim-control\examples\config.toml'
        else:
            args.config_path = r'C:\Users\Administrator\Projects\dispim-control\examples\config.toml'

        run = UserInterface(config_filepath=args.config_path,
                            console_output_level=args.log_level,
                            simulated=args.simulated)
