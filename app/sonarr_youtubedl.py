import argparse
import logging
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime

import requests
import schedule
import yt_dlp
from utils import (
    YoutubeDLLogger,
    checkconfig,
    offsethandler,
    setup_logging,
    upperescape,
    ytdl_hooks,
    ytdl_hooks_debug,
)

# allow debug arg for verbose logging
parser = argparse.ArgumentParser(description="Process some integers.")
parser.add_argument("--debug", action="store_true", help="Enable debug logging")
args = parser.parse_args()

# setup logger
logger = setup_logging(True, True, args.debug)

date_format = "%Y-%m-%dT%H:%M:%SZ"
now = datetime.now()

CONFIGFILE = os.environ["CONFIGPATH"]
CONFIGPATH = CONFIGFILE.replace("config.yml", "")
SCANINTERVAL = 60


class SonarrYTDL:
    def __init__(self):
        """Set up app with config file settings"""
        cfg = checkconfig()

        # Sonarr_YTDL Setup

        try:
            self.set_scan_interval(cfg["sonarrytdl"]["scan_interval"])
            try:
                self.debug = cfg["sonarrytdl"]["debug"]
                if self.debug:
                    logger.setLevel(logging.DEBUG)
                    for logs in logger.handlers:
                        if logs.name == "FileHandler":
                            logs.setLevel(logging.DEBUG)
                        if logs.name == "StreamHandler":
                            logs.setLevel(logging.DEBUG)
                    logger.debug("DEBUGGING ENABLED")
            except AttributeError:
                logger.exception("AttributeError")
                self.debug = False
        except Exception:
            logger.exception("Error with sonarrytdl config.yml values.")
            sys.exit()

        # Sonarr Setup
        try:
            api = "api"
            scheme = "http"
            basedir = ""
            if cfg["sonarr"].get("version", "").lower() == "v4":
                api = "api/v3"
                logger.debug("Sonarr api set to v4")
            if cfg["sonarr"]["ssl"]:
                scheme = "https"
            if cfg["sonarr"].get("basedir", ""):
                basedir = "/" + cfg["sonarr"].get("basedir", "")

            self.base_url = "{}://{}:{}{}".format(scheme, cfg["sonarr"]["host"], str(cfg["sonarr"]["port"]), basedir)
            self.sonarr_api_version = api
            self.api_key = cfg["sonarr"]["apikey"]
        except Exception:
            logger.exception("Error with sonarr config.yml values.")
            sys.exit()

        # YTDL Setup
        try:
            self.ytdl_format = cfg["ytdl"]["default_format"]
        except Exception:
            logger.exception("Error with ytdl config.yml values.")
            sys.exit()

        try:
            self.ytdl_merge_output_format = cfg["ytdl"]["merge_output_format"]
        except Exception:
            sys.exit("Error with ytdl config.yml values.")

        # YTDL Setup
        try:
            self.series = cfg["series"]
        except Exception:
            logger.exception("Error with series config.yml values.")
            sys.exit()

    def get_episodes_by_series_id(self, series_id):
        """Returns all episodes for the given series"""
        logger.debug(f"Begin call Sonarr for all episodes for series_id: {series_id}")
        args = {"seriesId": series_id}
        res = self.request_get(f"{self.base_url}/{self.sonarr_api_version}/episode", args)
        return res.json()

    def get_episode_files_by_series_id(self, series_id):
        """Returns all episode files for the given series"""
        res = self.request_get(f"{self.base_url}/{self.sonarr_api_version}/episodefile?seriesId={series_id}")
        return res.json()

    def get_series(self):
        """Return all series in your collection"""
        logger.debug("Begin call Sonarr for all available series")
        res = self.request_get(f"{self.base_url}/{self.sonarr_api_version}/series")
        return res.json()

    def get_series_by_series_id(self, series_id):
        """Return the series with the matching ID or 404 if no matching series is found"""
        logger.debug(f"Begin call Sonarr for specific series series_id: {series_id}")
        res = self.request_get(f"{self.base_url}/{self.sonarr_api_version}/series/{series_id}")
        return res.json()

    def request_get(self, url, params=None):
        """Wrapper on the requests.get"""
        logger.debug(f"Begin GET with url: {url}")
        args = {"apikey": self.api_key}
        if params is not None:
            logger.debug(f"Begin GET with params: {params}")
            args.update(params)
        url = f"{url}?{urllib.parse.urlencode(args)}"
        res = requests.get(url, timeout=10)
        return res

    def request_put(self, url, params=None, jsondata=None):
        logger.debug(f"Begin PUT with url: {url}")
        """Wrapper on the requests.put"""
        headers = {
            "Content-Type": "application/json",
        }
        args = (("apikey", self.api_key),)
        if params is not None:
            args.update(params)
            logger.debug(f"Begin PUT with params: {params}")
        res = requests.post(url, headers=headers, params=args, json=jsondata, timeout=10)
        return res

    def rescanseries(self, series_id):
        """Refresh series information from trakt and rescan disk"""
        logger.debug(f"Begin call Sonarr to rescan for series_id: {series_id}")
        data = {"name": "RescanSeries", "seriesId": str(series_id)}
        res = self.request_put(f"{self.base_url}/{self.sonarr_api_version}/command", None, data)
        return res.json()

    def filterseries(self):
        """Return all series in Sonarr that are to be downloaded by youtube-dl"""
        series = self.get_series()
        matched = []
        for ser in series[:]:
            for wnt in self.series:
                if wnt["title"] == ser["title"]:
                    # Set default values
                    ser["subtitles"] = False
                    ser["playlistreverse"] = True
                    ser["subtitles_languages"] = ["en"]
                    ser["subtitles_autogenerated"] = False
                    # Update values
                    if "regex" in wnt:
                        regex = wnt["regex"]
                        if "sonarr" in regex:
                            ser["sonarr_regex_match"] = regex["sonarr"]["match"]
                            ser["sonarr_regex_replace"] = regex["sonarr"]["replace"]
                        if "site" in regex:
                            ser["site_regex_match"] = regex["site"]["match"]
                            ser["site_regex_replace"] = regex["site"]["replace"]
                    if "offset" in wnt:
                        ser["offset"] = wnt["offset"]
                    if "cookies_file" in wnt:
                        ser["cookies_file"] = wnt["cookies_file"]
                    if "format" in wnt:
                        ser["format"] = wnt["format"]
                    if "playlistreverse" in wnt and wnt["playlistreverse"] == "False":
                        ser["playlistreverse"] = False
                    if "subtitles" in wnt:
                        ser["subtitles"] = True
                        if "languages" in wnt["subtitles"]:
                            ser["subtitles_languages"] = wnt["subtitles"]["languages"]
                        if "autogenerated" in wnt["subtitles"]:
                            ser["subtitles_autogenerated"] = wnt["subtitles"]["autogenerated"]
                    ser["url"] = wnt["url"]
                    if "preprend_with_title" in wnt:
                        ser["preprend_with_title"] = True
                    else:
                        ser["preprend_with_title"] = False
                    matched.append(ser)
        for check in matched:
            if not check["monitored"]:
                logger.warn("{} is not currently monitored".format(ser["title"]))
        del series[:]
        return matched

    def getseriesepisodes(self, series):
        needed = []
        for ser in series[:]:
            episodes = self.get_episodes_by_series_id(ser["id"])
            for eps in episodes[:]:
                eps_date = now
                if "airDateUtc" in eps:
                    eps_date = datetime.strptime(eps["airDateUtc"], date_format)
                    if "offset" in ser:
                        eps_date = offsethandler(eps_date, ser["offset"])
                if not eps["monitored"] or eps["hasFile"] or eps_date > now:
                    episodes.remove(eps)
                else:
                    if "sonarr_regex_match" in ser:
                        match = ser["sonarr_regex_match"]
                        replace = ser["sonarr_regex_replace"]
                        eps["title"] = re.sub(match, replace, eps["title"])
                    needed.append(eps)
                    continue
            if len(episodes) == 0:
                logger.info("{} no episodes needed".format(ser["title"]))
                series.remove(ser)
            else:
                logger.info("{} missing {} episodes".format(ser["title"], len(episodes)))
                for i, e in enumerate(episodes):
                    logger.info(f"  {i + 1}: {ser['title']} - {e['title']}")
        return needed

    def appendcookie(self, ytdlopts, cookies=None):
        """Checks if specified cookie file exists in config
        - ``ytdlopts``: Youtube-dl options to append cookie to
        - ``cookies``: filename of cookie file to append to Youtube-dl opts
        returns:
            ytdlopts
                original if problem with cookies file
                updated with cookies value if cookies file exists
        """
        if cookies is not None:
            cookie_path = os.path.abspath(CONFIGPATH + cookies)
            cookie_exists = os.path.exists(cookie_path)
            if cookie_exists is True:
                ytdlopts.update({"cookiefile": cookie_path})
                # if self.debug is True:
                logger.debug(f"  Cookies file used: {cookie_path}")
            if cookie_exists is False:
                logger.warning("  cookie files specified but doesnt exist.")
            return ytdlopts
        else:
            return ytdlopts

    def customformat(self, ytdlopts, customformat=None):
        """Checks if specified cookie file exists in config
        - ``ytdlopts``: Youtube-dl options to change the ytdl format for
        - ``customformat``: format to download
        returns:
            ytdlopts
                original: if no custom format
                updated: with new format value if customformat exists
        """
        if customformat is not None:
            ytdlopts.update({"format": customformat})
            return ytdlopts
        else:
            return ytdlopts

    def ytdl_eps_search_opts(self, regextitle, playlistreverse, cookies=None):
        ytdlopts = {
            "ignoreerrors": True,
            "playlistreverse": playlistreverse,
            "matchtitle": regextitle,
            "quiet": True,
        }
        if self.debug is True:
            ytdlopts.update({
                "quiet": False,
                "logger": YoutubeDLLogger(),
                "progress_hooks": [ytdl_hooks],
            })
        ytdlopts = self.appendcookie(ytdlopts, cookies)
        if self.debug is True:
            logger.debug("Youtube-DL opts used for episode matching")
            logger.debug(ytdlopts)
        return ytdlopts

    def ytsearch(self, ydl_opts, playlist):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(playlist, download=False)
        except Exception:
            logger.exception("extract_info failed")
        else:
            video_url = None
            entries = result.get("entries", None)
            if entries and entries != [None]:
                try:
                    video_url = entries[0].get("webpage_url")
                except Exception:
                    logger.exception("error getting video_url")
            else:
                video_url = result.get("webpage_url")
            if playlist == video_url:
                return False, ""
            if video_url is None:
                logger.error("No video_url")
                return False, ""
            else:
                return True, video_url

    def download(self, series, episodes):
        if len(series) != 0:
            logger.info("Processing Wanted Downloads")
            for _s, ser in enumerate(series):
                logger.info("  {}:".format(ser["title"]))
                for e, eps in enumerate(episodes):
                    if ser["id"] == eps["seriesId"]:
                        cookies = None
                        url = ser["url"]
                        eps_title = (
                            f"{ser['title']} - {eps['title']}"
                            if ser.get("preprend_with_title", False)
                            else eps["title"]
                        )
                        if "cookies_file" in ser:
                            cookies = ser["cookies_file"]
                        ydleps = self.ytdl_eps_search_opts(upperescape(eps_title), ser["playlistreverse"], cookies)
                        found, dlurl = self.ytsearch(ydleps, url)
                        if found:
                            logger.info(f"    {e + 1}: Found - {eps_title}")

                            # Remove colons from series and episode titles
                            episode_title_no_colon = eps["title"].replace(":", "").replace("  ", " ")
                            ser_title_no_colon = ser["title"].replace(":", "")

                            ytdl_format_options = {
                                "format": self.ytdl_format,
                                "quiet": True,
                                "merge_output_format": self.ytdl_merge_output_format,
                                "outtmpl": "/sonarr_root{0}/Season {1}/{2}.S{1}E{3:02d}.{4}.%(ext)s".format(
                                    ser["path"],
                                    eps["seasonNumber"],
                                    ser_title_no_colon,
                                    eps["episodeNumber"],
                                    episode_title_no_colon,
                                ),
                                "progress_hooks": [ytdl_hooks],
                                "noplaylist": True,
                            }
                            ytdl_format_options = self.appendcookie(ytdl_format_options, cookies)
                            if "format" in ser:
                                ytdl_format_options = self.customformat(ytdl_format_options, ser["format"])

                            # Init postprocessors
                            postprocessors = []

                            if ser.get("subtitles"):
                                postprocessors.append({
                                    "key": "FFmpegSubtitlesConvertor",
                                    "format": "srt",
                                })
                                postprocessors.append({
                                    "key": "FFmpegEmbedSubtitle",
                                })
                                ytdl_format_options.update({
                                    "writesubtitles": True,
                                    "allsubtitles": True,
                                    "writeautomaticsub": True,
                                    "subtitleslangs": ser["subtitles_languages"],
                                    "embedsubtitles": True,
                                })

                            # Add postprocessors
                            ytdl_format_options.update({"postprocessors": postprocessors})

                            if self.debug is True:
                                ytdl_format_options.update({
                                    "quiet": False,
                                    "logger": YoutubeDLLogger(),
                                    "progress_hooks": [ytdl_hooks_debug],
                                })
                                logger.debug("Youtube-DL opts used for downloading")
                                logger.debug(ytdl_format_options)
                            try:
                                yt_dlp.YoutubeDL(ytdl_format_options).download([dlurl])
                                self.rescanseries(ser["id"])
                                logger.info(f"      Downloaded - {eps_title}")
                            except Exception:
                                logger.exception(f"      Failed - {eps_title}")
                        else:
                            logger.info(f"    {e + 1}: Missing - {eps_title}")
        else:
            logger.info("Nothing to process")

    def set_scan_interval(self, interval):
        global SCANINTERVAL
        if interval != SCANINTERVAL:
            SCANINTERVAL = interval
            logger.info(f"Scan interval set to every {interval} minutes by config.yml")
        else:
            logger.info(f"Default scan interval of every {interval} minutes in use")
        return


def main():
    client = SonarrYTDL()
    series = client.filterseries()
    episodes = client.getseriesepisodes(series)
    client.download(series, episodes)
    logger.info("Waiting...")


if __name__ == "__main__":
    logger.info("Initial run")
    main()
    schedule.every(int(SCANINTERVAL)).minutes.do(main)
    while True:
        schedule.run_pending()
        time.sleep(1)
