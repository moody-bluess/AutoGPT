"""Commands to search the web with"""

from __future__ import annotations

import os
import socket

import httplib2

COMMAND_CATEGORY = "web_search"
COMMAND_CATEGORY_TITLE = "Web Search"

import json
import time
from itertools import islice

from duckduckgo_search import DDGS

from autogpt.agents.agent import Agent
from autogpt.command_decorator import command

DUCKDUCKGO_MAX_ATTEMPTS = 3

QUNAR_PROXY_HOST = os.environ.get("QUNAR_PROXY_HOST")
QUNAR_PROXY_PORT = os.environ.get("QUNAR_PROXY_PORT")
QUNAR_PROXY_USR = os.environ.get("QUNAR_PROXY_USR")
QUNAR_PROXY_PWD = os.environ.get("QUNAR_PROXY_PWD")
proxies = {
    'http': f'http://{QUNAR_PROXY_HOST}:{QUNAR_PROXY_PORT}',
    'https': f'http://{QUNAR_PROXY_HOST}:{QUNAR_PROXY_PORT}'
}


@command(
    "web_search",
    "Searches the web",
    {
        "query": {
            "type": "string",
            "description": "The search query",
            "required": True,
        }
    },
    aliases=["search"],
)
def web_search(query: str, agent: Agent, num_results: int = 8) -> str:
    """Return the results of a Google search

    Args:
        query (str): The search query.
        num_results (int): The number of results to return.

    Returns:
        str: The results of the search.
    """
    search_results = []
    attempts = 0

    while attempts < DUCKDUCKGO_MAX_ATTEMPTS:
        if not query:
            return json.dumps(search_results)

        results = DDGS(proxies=proxies).text(query)
        search_results = list(islice(results, num_results))

        if search_results:
            break

        time.sleep(1)
        attempts += 1

    results = json.dumps(search_results, ensure_ascii=False, indent=4)
    return safe_google_results(results)


@command(
    "google",
    "Google Search",
    {
        "query": {
            "type": "string",
            "description": "The search query",
            "required": True,
        }
    },
    lambda config: bool(config.google_api_key)
                   and bool(config.google_custom_search_engine_id),
    "Configure google_api_key and custom_search_engine_id.",
    aliases=["search"],
)
def google(query: str, agent: Agent, num_results: int = 8) -> str | list[str]:
    """Return the results of a Google search using the official Google API

    Args:
        query (str): The search query.
        num_results (int): The number of results to return.

    Returns:
        str: The results of the search.
    """

    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    try:
        # Get the Google API key and Custom Search Engine ID from the config file
        api_key = agent.config.google_api_key
        custom_search_engine_id = agent.config.google_custom_search_engine_id

        # Initialize the Custom Search API service
        service = build("customsearch", "v1", developerKey=api_key, http=build_http_proxy())

        # Send the search query and retrieve the results
        result = (
            service.cse()
                .list(q=query, cx=custom_search_engine_id, num=num_results)
                .execute()
        )

        # Extract the search result items from the response
        search_results = result.get("items", [])

        # Create a list of only the URLs from the search results
        search_results_links = [item["link"] for item in search_results]

    except HttpError as e:
        # Handle errors in the API call
        error_details = json.loads(e.content.decode())

        # Check if the error is related to an invalid or missing API key
        if error_details.get("error", {}).get(
                "code"
        ) == 403 and "invalid API key" in error_details.get("error", {}).get(
            "message", ""
        ):
            return "Error: The provided Google API key is invalid or missing."
        else:
            return f"Error: {e}"
    # google_result can be a list or a string depending on the search results

    # Return the list of search result URLs
    return safe_google_results(search_results_links)


def safe_google_results(results: str | list) -> str:
    """
        Return the results of a Google search in a safe format.

    Args:
        results (str | list): The search results.

    Returns:
        str: The results of the search.
    """
    if isinstance(results, list):
        safe_message = json.dumps(
            [result.encode("utf-8", "ignore").decode("utf-8") for result in results]
        )
    else:
        safe_message = results.encode("utf-8", "ignore").decode("utf-8")
    return safe_message


def build_http_proxy():
    """Builds httplib2.Http object

    Returns:
    A httplib2.Http object, which is used to make http requests, and which has timeout set by default.
    To override default timeout call

      socket.setdefaulttimeout(timeout_in_sec)

    before interacting with this method.
    """
    if socket.getdefaulttimeout() is not None:
        http_timeout = socket.getdefaulttimeout()
    else:
        http_timeout = 60
    http = httplib2.Http(timeout=http_timeout, proxy_info=proxy_info_from_url())
    # 308's are used by several Google APIs (Drive, YouTube)
    # for Resumable Uploads rather than Permanent Redirects.
    # This asks httplib2 to exclude 308s from the status codes
    # it treats as redirects
    try:
        http.redirect_codes = http.redirect_codes - {308}
    except AttributeError:
        # Apache Beam tests depend on this library and cannot
        # currently upgrade their httplib2 version
        # http.redirect_codes does not exist in previous versions
        # of httplib2, so pass
        pass

    return http


def proxy_info_from_url(method="http", noproxy=None):
    """Construct a ProxyInfo from a URL (such as http_proxy env var)
    """

    proxy_type = 3  # socks.PROXY_TYPE_HTTP
    pi = httplib2.ProxyInfo(
        proxy_type=proxy_type,
        proxy_host=QUNAR_PROXY_HOST,
        proxy_port=QUNAR_PROXY_PORT or dict(https=443, http=80)[method],
        proxy_user=QUNAR_PROXY_USR or None,
        proxy_pass=QUNAR_PROXY_PWD or None,
        proxy_headers=None,
    )

    bypass_hosts = []
    # If not given an explicit noproxy value, respect values in env vars.
    if noproxy is None:
        noproxy = os.environ.get("no_proxy", os.environ.get("NO_PROXY", ""))
    # Special case: A single '*' character means all hosts should be bypassed.
    if noproxy == "*":
        bypass_hosts = httplib2.AllHosts
    elif noproxy.strip():
        bypass_hosts = noproxy.split(",")
        bypass_hosts = tuple(filter(bool, bypass_hosts))  # To exclude empty string.

    pi.bypass_hosts = bypass_hosts
    return pi
