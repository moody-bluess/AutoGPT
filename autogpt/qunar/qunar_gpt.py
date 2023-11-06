import os

import openai
from openai import api_requestor, error, util
from openai.api_resources.abstract.api_resource import APIResource
from openai.openai_response import OpenAIResponse
from openai.util import ApiType

from autogpt.qunar.qunar_requestor import QunarRequestor

MAX_TIMEOUT = 20


class QunarGPT:
    plain_old_data = False

    @classmethod
    def create(
            cls,
            api_key=None,
            api_base=None,
            api_type=None,
            request_id=None,
            api_version=None,
            organization=None,
            **params,
    ):
        (
            deployment_id,
            engine,
            timeout,
            stream,
            headers,
            request_timeout,
            typed_api_type,
            requestor,
            url,
            params,
        ) = cls.__prepare_create_request(
            api_key, api_base, api_type, api_version, organization, **params
        )

        response, _, api_key = requestor.request(
            "post",
            url,
            params=params,
            headers=headers,
            stream=stream,
            request_id=request_id,
            request_timeout=request_timeout,
        )

        if stream:
            # must be an iterator
            assert not isinstance(response, OpenAIResponse)
            return (
                util.convert_to_openai_object(
                    line,
                    api_key,
                    api_version,
                    organization,
                    engine=engine,
                    plain_old_data=cls.plain_old_data,
                )
                for line in response
            )
        else:
            obj = util.convert_to_openai_object(
                response,
                api_key,
                api_version,
                organization,
                engine=engine,
                plain_old_data=cls.plain_old_data,
            )

            if timeout is not None:
                obj.wait(timeout=timeout or None)

        return obj

    @classmethod
    def __prepare_create_request(
            cls,
            api_key=None,
            api_base=None,
            api_type=None,
            api_version=None,
            organization=None,
            **params,
    ):
        deployment_id = params.pop("deployment_id", None)
        engine = params.pop("engine", deployment_id)
        model = params.get("model", None)
        timeout = params.pop("timeout", None)
        stream = params.get("stream", False)
        headers = params.pop("headers", None)
        request_timeout = params.pop("request_timeout", None)
        typed_api_type = None
        if typed_api_type in (util.ApiType.AZURE, util.ApiType.AZURE_AD):
            if deployment_id is None and engine is None:
                raise error.InvalidRequestError(
                    "Must provide an 'engine' or 'deployment_id' parameter to create a %s"
                    % cls,
                    "engine",
                )
        else:
            if model is None and engine is None:
                raise error.InvalidRequestError(
                    "Must provide an 'engine' or 'model' parameter to create a %s"
                    % cls,
                    "engine",
                )

        if timeout is None:
            # No special timeout handling
            pass
        elif timeout > 0:
            # API only supports timeouts up to MAX_TIMEOUT
            params["timeout"] = min(timeout, MAX_TIMEOUT)
            timeout = (timeout - params["timeout"]) or None
        elif timeout == 0:
            params["timeout"] = MAX_TIMEOUT

        requestor = QunarRequestor(
            api_key,
            api_base=api_base,
            api_type=api_type,
            api_version=api_version,
            organization=organization,
        )
        # url = cls.class_url(engine, api_type, api_version)
        url = None
        return (
            deployment_id,
            engine,
            timeout,
            stream,
            headers,
            request_timeout,
            typed_api_type,
            requestor,
            url,
            params,
        )
