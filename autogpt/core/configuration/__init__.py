"""The configuration encapsulates settings for all Agent subsystems."""
import os

from autogpt.core.configuration.schema import (
    Configurable,
    SystemConfiguration,
    SystemSettings,
    UserConfigurable,
)
QUNAR_PROXY_HOST = os.environ.get("QUNAR_PROXY_HOST")
QUNAR_PROXY_PORT = os.environ.get("QUNAR_PROXY_PORT")
QUNAR_PROXY_USR = os.environ.get("QUNAR_PROXY_USR")
QUNAR_PROXY_PWD = os.environ.get("QUNAR_PROXY_PWD")
QUNAR_APPCODE = os.environ.get("QUNAR_APPCODE")
proxies = {
    'http': f'http://{QUNAR_PROXY_HOST}:{QUNAR_PROXY_PORT}',
    'https': f'http://{QUNAR_PROXY_HOST}:{QUNAR_PROXY_PORT}'
}