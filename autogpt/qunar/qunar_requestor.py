import json
import os
import threading
import time
import warnings
from json import JSONDecodeError
from typing import (
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Dict,
    Iterator,
    Optional,
    Tuple,
    Union,
    overload,
)

import openai
import requests
from openai import error, util, api_requestor
from openai.openai_response import OpenAIResponse
from openai.util import ApiType

TIMEOUT_SECS = 600
MAX_SESSION_LIFETIME_SECS = 180
MAX_CONNECTION_RETRIES = 2
api_base = os.environ.get("QUNAR_API_BASE", "http://llm.api.corp.qunar.com/algo/llm/api")
_thread_context = threading.local()
requestssession: Optional[
    Union["requests.Session", Callable[[], "requests.Session"]]
] = None  # Provide a requests.Session or Session factory.
verify_ssl_certs = True
proxy = None

QUNAR_GPT_MODEL = os.environ.get("QUNAR_GPT_MODEL", 'gpt-4')
QUNAR_KEY = os.environ.get("QUNAR_KEY")
QUNAR_PWD = os.environ.get("QUNAR_PWD")
QUNAR_USER = os.environ.get("QUNAR_USER", 'lianchen.zhang')


class QunarRequestor:

    def __init__(
            self,
            key=None,
            api_base=None,
            api_type=None,
            api_version=None,
            organization=None,
    ):
        self.api_base = api_base or api_base
        self.api_key = key or util.default_api_key()
        self.api_type = (
            ApiType.from_str(api_type)
            if api_type
            else ApiType.from_str(openai.api_type)
        )
        self.api_version = api_version or openai.api_version
        self.organization = organization or openai.organization

    def request(
            self,
            method,
            url,
            params=None,
            headers=None,
            files=None,
            stream: bool = False,
            request_id: Optional[str] = None,
            request_timeout: Optional[Union[float, Tuple[float, float]]] = None,
    ) -> Tuple[Union[OpenAIResponse, Iterator[OpenAIResponse]], bool, str]:
        result = self.request_raw(
            method.lower(),
            url,
            params=params,
            supplied_headers=headers,
            files=files,
            stream=stream,
            request_id=request_id,
            request_timeout=request_timeout,
        )
        resp, got_stream = self._interpret_response(result, stream)
        return resp, got_stream, self.api_key

    def _interpret_response(
            self, result: requests.Response, stream: bool
    ) -> Tuple[Union[OpenAIResponse, Iterator[OpenAIResponse]], bool]:
        """Returns the response(s) and a bool indicating whether it is a stream."""
        if stream and "text/event-stream" in result.headers.get("Content-Type", ""):
            pass
            # return (
            #     self._interpret_response_line(
            #         line, result.status_code, result.headers, stream=True
            #     )
            #     for line in parse_stream(result.iter_lines())
            # ), True
        else:
            return (
                self._interpret_response_line(
                    result.content.decode("utf-8"),
                    result.status_code,
                    result.headers,
                    stream=False,
                ),
                False,
            )

    def _interpret_response_line(
            self, rbody: str, rcode: int, rheaders, stream: bool
    ) -> OpenAIResponse:
        # HTTP 204 response code does not have any content in the body.
        if rcode == 204:
            return OpenAIResponse(None, rheaders)

        if rcode == 503:
            raise error.ServiceUnavailableError(
                "The server is overloaded or not ready yet.",
                rbody,
                rcode,
                headers=rheaders,
            )
        try:
            if 'text/plain' in rheaders.get('Content-Type', ''):
                data = rbody
            else:
                data = json.loads(rbody)
        except (JSONDecodeError, UnicodeDecodeError) as e:
            raise error.APIError(
                f"HTTP code {rcode} from API ({rbody})", rbody, rcode, headers=rheaders
            ) from e

        if data.get("status") != 0:
            raise error.APIError(f"API error with msg {data.get('message')}")
        content = data.get("data")
        reply = content.get("reply")

        new_data = {}
        message = {'role': 'assistant', 'content': reply}
        choices = [{'message': message}]
        new_data['choices'] = choices
        new_data['usage'] = {
            'prompt_tokens': content['usage'],
            'completion_tokens': 0,
            'total_tokens': content['usage']
        }
        new_data['model'] = 'gpt-3.5-turbo-0613'
        resp = OpenAIResponse(new_data, rheaders)
        # In the future, we might add a "status" parameter to errors
        # to better handle the "error while streaming" case.
        stream_error = stream and "error" in resp.data
        if stream_error or not 200 <= rcode < 300:
            raise api_requestor.APIRequestor.handle_error_response(
                rbody, rcode, resp.data, rheaders, stream_error=stream_error
            )
        return resp

    def request_raw(
            self,
            method,
            url,
            *,
            params=None,
            supplied_headers: Optional[Dict[str, str]] = None,
            files=None,
            stream: bool = False,
            request_id: Optional[str] = None,
            request_timeout: Optional[Union[float, Tuple[float, float]]] = None,
    ) -> requests.Response:
        abs_url, headers, data = self._prepare_request_raw(
            url, supplied_headers, method, params, files, request_id
        )

        if not hasattr(_thread_context, "session"):
            _thread_context.session = _make_session()
            _thread_context.session_create_time = time.time()
        elif (
                time.time() - getattr(_thread_context, "session_create_time", 0)
                >= MAX_SESSION_LIFETIME_SECS
        ):
            _thread_context.session.close()
            _thread_context.session = _make_session()
            _thread_context.session_create_time = time.time()
        try:
            result = _thread_context.session.request(
                method,
                abs_url,
                headers=headers,
                data=data,
                files=files,
                stream=stream,
                timeout=request_timeout if request_timeout else TIMEOUT_SECS,
                proxies=_thread_context.session.proxies,
            )
        except requests.exceptions.Timeout as e:
            raise error.Timeout("Request timed out: {}".format(e)) from e
        except requests.exceptions.RequestException as e:
            raise error.APIConnectionError(
                "Error communicating with OpenAI: {}".format(e)
            ) from e
        util.log_debug(
            "OpenAI API response",
            path=abs_url,
            response_code=result.status_code,
            processing_ms=result.headers.get("OpenAI-Processing-Ms"),
            request_id=result.headers.get("X-Request-Id"),
        )
        # Don't read the whole stream for debug logging unless necessary.
        return result

    def _prepare_request_raw(
            self,
            url,
            supplied_headers,
            method,
            params,
            files,
            request_id: Optional[str],
    ) -> Tuple[str, Dict[str, str], Optional[bytes]]:

        abs_url = api_base

        headers = {}

        request_body = {
            "key": QUNAR_KEY,
            "password": QUNAR_PWD,
            "apiVersion": "2023-05-15",
            "appCode": "-----",
            "traceId": "123",
            "userIdentityInfo": QUNAR_USER,
            "version": "hard",
            "project": "售后客服对话总结"
        }

        prompt = {
            "top_p": 1,
            "n": 1,
            "frequency_penalty": 0,
            "presence_penalty": 0,
        }
        prompt["messages"] = params["messages"]
        prompt["temperature"] = params["temperature"]
        request_body["prompt"] = prompt
        # request_body["apiType"] = params["model"]
        request_body["apiType"] = QUNAR_GPT_MODEL
        max_tokens = params['max_tokens']

        data = None
        if method == "get" or method == "delete":
            pass
            # if params:
            #     encoded_params = urlencode(
            #         [(k, v) for k, v in params.items() if v is not None]
            #     )
            #     abs_url = _build_api_url(abs_url, encoded_params)
        elif method in {"post", "put"}:
            # TODO
            if request_body and files:
                data = request_body
            if request_body and not files:
                data = json.dumps(request_body).encode()
                headers["Content-Type"] = "application/json"
        else:
            raise error.APIConnectionError(
                "Unrecognized HTTP method %r. This may indicate a bug in the "
                "OpenAI bindings. Please contact us through our help center at help.openai.com for "
                "assistance." % (method,)
            )

        util.log_debug("Request to OpenAI API", method=method, path=abs_url)
        util.log_debug("Post details", data=data, api_version=self.api_version)

        return abs_url, headers, data


def _make_session() -> requests.Session:
    if requestssession:
        if isinstance(requestssession, requests.Session):
            return requestssession
        return requestssession()
    if not verify_ssl_certs:
        warnings.warn("verify_ssl_certs is ignored; openai always verifies.")
    s = requests.Session()
    proxies = _requests_proxies_arg(proxy)
    if proxies:
        s.proxies = proxies
    s.mount(
        "https://",
        requests.adapters.HTTPAdapter(max_retries=MAX_CONNECTION_RETRIES),
    )
    return s


def _requests_proxies_arg(proxy) -> Optional[Dict[str, str]]:
    """Returns a value suitable for the 'proxies' argument to 'requests.request."""
    if proxy is None:
        return None
    elif isinstance(proxy, str):
        return {"http": proxy, "https": proxy}
    elif isinstance(proxy, dict):
        return proxy.copy()
    else:
        raise ValueError(
            "'openai.proxy' must be specified as either a string URL or a dict with string URL under the https and/or http keys."
        )
