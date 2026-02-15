import argparse
import logging
import sys

from fimcontextserver._server import Server


def main():
    parser = argparse.ArgumentParser(description="FIM context server")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    server = Server()
    server.run()


main()
