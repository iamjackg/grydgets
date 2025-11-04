"""REST API data provider."""

import base64
import requests

from grydgets.providers.base import DataProvider
from grydgets.json_utils import extract_data


class RestDataProvider(DataProvider):
    """Data provider that fetches data from REST APIs.

    Supports all features from RESTWidget:
    - HTTP methods (GET, POST, PUT, DELETE)
    - Authentication (Basic, Bearer)
    - Custom headers and query parameters
    - JSON path extraction
    - Jitter for update intervals
    """

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
        """Initialize the REST data provider.

        Args:
            url: The URL to fetch from
            method: HTTP method (GET, POST, PUT, DELETE) (default: GET)
            headers: Dictionary of HTTP headers
            params: Dictionary of query parameters
            body: Request body for POST/PUT
            auth: Authentication dict with 'type' and credentials
            json_path: JSON path to extract from response
            jq_expression: jq expression to extract from response
            payload: Alias for body (for compatibility)
            **kwargs: Additional arguments passed to DataProvider
        """
        super().__init__(**kwargs)

        self.url = url
        self.method = method.upper()
        self.headers = headers or {}
        self.params = params or {}
        self.body = body or payload
        self.json_path = json_path
        self.jq_expression = jq_expression

        # Build request kwargs
        self.requests_kwargs = {
            "headers": dict(self.headers),
            "params": self.params,
        }

        # Configure authentication
        if auth is not None:
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

        # Add body for POST/PUT requests
        if self.method in ("POST", "PUT") and self.body:
            self.requests_kwargs["json"] = self.body

    def _fetch_data(self):
        """Fetch data from the REST API.

        Returns:
            The fetched data, optionally extracted via json_path and/or jq_expression.

        Raises:
            requests.RequestException: If the HTTP request fails
            Exception: If JSON extraction fails
        """
        response = requests.request(
            method=self.method,
            url=self.url,
            **self.requests_kwargs
        )

        if response.status_code != 200:
            raise Exception(f"HTTP {response.status_code}: {response.text}")

        # Parse JSON response
        try:
            data = response.json()
        except ValueError as e:
            raise Exception(f"Invalid JSON response: {e}")

        # Extract data if json_path or jq_expression specified
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
