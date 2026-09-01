"""REST API data provider."""

import base64
import requests

from grydgets.providers.base import DataProvider
from grydgets.json_utils import extract_data


class RestDataProvider(DataProvider):
    """Fetches data from a REST API: HTTP methods, basic/bearer auth, and
    JSON/jq extraction, matching what RESTWidget supports."""

    def __init__(
        self,
        url,
        method="GET",
        headers=None,
        params=None,
        body=None,
        auth=None,
        json_path=None,
        jq_expression=None,
        payload=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.params = params or {}
        # payload is an accepted alias for body.
        self.body = body or payload
        self.json_path = json_path
        self.jq_expression = jq_expression

        self.requests_kwargs = {
            "headers": dict(self.headers),
            "params": self.params,
        }

        if auth is not None:
            # Accepts both the {"bearer": token} shorthand and the
            # {"type": "bearer"/"basic", ...} form.
            if "bearer" in auth:
                self.requests_kwargs["headers"]["Authorization"] = f"Bearer {auth['bearer']}"
            elif "basic" in auth:
                username = auth["basic"].get("username", "")
                password = auth["basic"].get("password", "")
                auth_string = f"{username}:{password}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                self.requests_kwargs["headers"]["Authorization"] = f"Basic {encoded_auth}"
            elif auth.get("type") == "bearer" and "token" in auth:
                self.requests_kwargs["headers"]["Authorization"] = f"Bearer {auth['token']}"
            elif auth.get("type") == "basic":
                username = auth.get("username", "")
                password = auth.get("password", "")
                auth_string = f"{username}:{password}"
                encoded_auth = base64.b64encode(auth_string.encode()).decode()
                self.requests_kwargs["headers"]["Authorization"] = f"Basic {encoded_auth}"

        if self.method in ("POST", "PUT") and self.body:
            self.requests_kwargs["json"] = self.body

    def _fetch_data(self):
        response = requests.request(
            method=self.method,
            url=self.url,
            **self.requests_kwargs
        )

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        try:
            data = response.json()
        except ValueError as e:
            raise Exception(f"Invalid JSON response: {e}")

        if self.json_path or self.jq_expression:
            try:
                data = extract_data(
                    data,
                    json_path=self.json_path,
                    jq_expression=self.jq_expression
                )
            except Exception as e:
                raise Exception(f"Data extraction failed: {e}")

        return data
