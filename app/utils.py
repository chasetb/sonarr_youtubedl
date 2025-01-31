import datetime
import logging
import os
import re
import sys
from logging.handlers import RotatingFileHandler

import yaml

CONFIGFILE = os.environ["CONFIGPATH"]
# CONFIGPATH = CONFIGFILE.replace('config.yml', '')


def sanitize_filename(name, replacement=" -"):
    """
    Sanitize a string to be used as a safe filename.

    Parameters:
        name (str): The original filename string.
        replacement (str): The character to replace invalid characters with.

    Returns:
        str: A sanitized filename string.
    """
    # Define a pattern for invalid characters (based on Windows, macOS, and Linux restrictions)
    invalid_chars = r'[<>:"/\\|?*\n\r\t]'
    # Replace invalid characters with the specified replacement character
    sanitized_name = re.sub(invalid_chars, replacement, name)

    # Remove leading and trailing whitespace & double spaces
    sanitized_name = sanitized_name.strip()
    sanitized_name = sanitized_name.replace("  ", " ")

    # Optionally, limit the length of the filename
    max_length = 255  # Max filename length for most filesystems
    return sanitized_name[:max_length]


def upperescape(string):
    """Uppercase and Escape string. Used to help with YT-DL regex match.
    - ``string``: string to manipulate

    returns:
        ``string``: str new string
    """
    # Convert to uppercase as YTDL is case-insensitive for ease.
    string = string.upper()

    # Normalize hyphens and en dashes for consistent matching
    string = string.replace("–", "-")  # Replace en dash with a regular hyphen # noqa: RUF001

    # Escape parentheses to match them as literal characters in the final regex pattern
    string = string.replace("(", r"\(")  # escape opening parenthesis
    string = string.replace(")", r"\)")  # escape closing parenthesis

    # Make punctuation optional and handle certain punctuation patterns
    string = string.replace(":", "([:]?)")  # optional colon
    string = string.replace("'", "(['’]?)")  # optional apostrophe  # noqa: RUF001
    string = string.replace(",", "([,]?)")  # optional comma
    string = string.replace("!", "([!]?)")  # optional exclamation mark
    string = string.replace("\\?", "([\\?]?)")  # optional question mark
    string = string.replace("\\.", "([\\.]?)")  # optional period

    # Replace " AND " or " & " with an appropriate regex match
    string = string.replace("\\ AND\\ ", "\\ (AND|&)\\ ")

    # Make hyphens optional or interchangeable with other punctuation
    # This handles cases where a dash or hyphen might differ between titles
    # This substitution ensures sequences of hyphens or dashes match
    # a set of hyphens and dashes in the original string.
    string = string.replace("-", "([-–]??)")  # noqa: RUF001

    # Replace optional belonging apostrophe before the `S` if present
    # The pattern "S\\\\" matches an `S` followed by a backslash.
    # The replacement ensures that there can be an optional apostrophe before `S\`
    string = re.sub("S\\\\", "([']?)S\\\\", string)

    # Use regex sub to handle spaces
    string = string.replace(" ", r"\s*")

    return string


def checkconfig():
    """Checks if config files exist in config path
    If no config available, will copy template to config folder and exit script

    returns:

        `cfg`: dict containing configuration values
    """
    logger = logging.getLogger("sonarr_youtubedl")
    config_template = os.path.abspath(CONFIGFILE + ".template")
    config_template_exists = os.path.exists(os.path.abspath(config_template))
    config_file = os.path.abspath(CONFIGFILE)
    config_file_exists = os.path.exists(os.path.abspath(config_file))
    if not config_file_exists:
        logger.critical("Configuration file not found.")  # print('Configuration file not found.')
        if not config_template_exists:
            command = f"cp /app/config.yml.template {config_template}"
            os.system(command)  # noqa: S605
        logger.critical(
            "Create a config.yml using config.yml.template as an example."
        )  # sys.exit("Create a config.yml using config.yml.template as an example.")
        sys.exit()
    else:
        logger.info("Configuration Found. Loading file.")  # print('Configuration Found. Loading file.')
        with open(config_file) as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
        return cfg


def offsethandler(airdate, offset):
    """Adjusts an episodes airdate
    - ``airdate``: Airdate from sonarr # (datetime)
    - ``offset``: Offset from series config.yml # (dict)

    returns:
        ``airdate``: datetime updated original airdate
    """
    weeks = 0
    days = 0
    hours = 0
    minutes = 0
    if "weeks" in offset:
        weeks = int(offset["weeks"])
    if "days" in offset:
        days = int(offset["days"])
    if "hours" in offset:
        hours = int(offset["hours"])
    if "minutes" in offset:
        minutes = int(offset["minutes"])
    airdate = airdate + datetime.timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes)
    return airdate


class YoutubeDLLogger:
    def __init__(self):
        self.logger = logging.getLogger("sonarr_youtubedl")

    def info(self, msg: str) -> None:
        self.logger.info(msg)

    def debug(self, msg: str) -> None:
        self.logger.debug(msg)

    def warning(self, msg: str) -> None:
        self.logger.info(msg)

    def error(self, msg: str) -> None:
        self.logger.error(msg)


def ytdl_hooks_debug(d):
    logger = logging.getLogger("sonarr_youtubedl")
    if d["status"] == "finished":
        file_tuple = os.path.split(os.path.abspath(d["filename"]))
        logger.info(f"      Done downloading {file_tuple[1]}")  # print("Done downloading {}".format(file_tuple[1]))
    if d["status"] == "downloading":
        progress = "      {} - {} - {}".format(d["filename"], d["_percent_str"], d["_eta_str"])
        logger.debug(progress)


def ytdl_hooks(d):
    logger = logging.getLogger("sonarr_youtubedl")
    if d["status"] == "finished":
        file_tuple = os.path.split(os.path.abspath(d["filename"]))
        logger.info(f"      Downloaded - {file_tuple[1]}")


def setup_logging(lf_enabled=True, lc_enabled=True, debugging=False):
    log_level = logging.INFO
    log_level = logging.DEBUG if debugging else log_level
    logger = logging.getLogger("sonarr_youtubedl")
    logger.setLevel(log_level)
    log_format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    if lf_enabled:
        # setup logfile
        log_file = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "logs"))
        log_file = os.path.abspath(log_file + "/sonarr_youtubedl.log")
        loggerfile = RotatingFileHandler(log_file, maxBytes=5000000, backupCount=5)
        loggerfile.setLevel(log_level)
        loggerfile.set_name("FileHandler")
        loggerfile.setFormatter(log_format)
        logger.addHandler(loggerfile)

    if lc_enabled:
        # setup console log
        loggerconsole = logging.StreamHandler()
        loggerconsole.setLevel(log_level)
        loggerconsole.set_name("StreamHandler")
        loggerconsole.setFormatter(log_format)
        logger.addHandler(loggerconsole)

    return logger
