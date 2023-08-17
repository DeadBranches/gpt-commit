"""
Initialize logging for this module.
"""
import logging
import textwrap

# Constants
DEFAULT_LOG_LEVEL = logging.INFO


class MultiLineFormatter(logging.Formatter):
    def format(self, record):
        message = record.msg
        record.msg = ""
        header = super().format(record)
        msg = textwrap.indent(message, " " * len(header)).lstrip()
        record.msg = message
        return header + msg


formatter = MultiLineFormatter(
    # fmt='%(asctime)s %(levelname)-8s %(message)s',
    fmt="[%(lineno)d] %(levelname)s - %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log_handler = logging.StreamHandler()
log_handler.setFormatter(formatter)

logging.basicConfig(
    level=DEFAULT_LOG_LEVEL,
    # formatter=formatter
    format="[%(lineno)d] %(levelname)s - %(name)s - %(message)s",
)
