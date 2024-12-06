# MIT License
#
# Copyright (c) 2024 Ramón Vila Ferreres
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import pytest
import asyncio

from tinybus.models import DeliveryOptions, Message
from fixtures import TestRequest, TestResponse
from tinybus.exceptions import HandlerExecutionError, HandlerTimeoutError


@pytest.mark.asyncio
async def test_handler_exceptions(event_bus):
    """Test various handler exception scenarios"""

    # Test uncontrolled exception
    async def failing_handler(msg):
        raise ValueError("Unexpected error")

    event_bus.consumer("failing.address", failing_handler)

    with pytest.raises(HandlerExecutionError) as exc_info:
        await event_bus.request("failing.address", TestRequest(value="test"))
    assert "Unexpected error" in str(exc_info.value)
    assert isinstance(exc_info.value.original_error, ValueError)

    # Test timeout with cleanup
    async def timeout_handler(msg):
        try:
            await asyncio.sleep(2)
            return TestResponse(result="too late")
        except asyncio.CancelledError:
            # Ensure cleanup happens
            # Perform any necessary cleanup here
            raise  # Allow the cancellation to propagate

    event_bus.consumer("timeout.address", timeout_handler)

    with pytest.raises(HandlerTimeoutError) as exc_info:
        await event_bus.request(
            "timeout.address",
            TestRequest(value="test"),
            options=DeliveryOptions(timeout=0.1)
        )
    assert exc_info.value.timeout == 0.1
    assert exc_info.value.address == "timeout.address"

    # Test handler returning None
    async def none_handler(msg):
        return None

    event_bus.consumer("none.address", none_handler)
    response = await event_bus.request("none.address", TestRequest(value="test"))
    assert response is None

    # Test handler with invalid return type
    async def invalid_handler(msg: Message[TestRequest]) -> TestResponse:
        return {"invalid": "response"}  # noqa Not a proper TestResponse model

    event_bus.consumer("invalid.address", invalid_handler)
    with pytest.raises(HandlerExecutionError) as exc_info:
        await event_bus.request("invalid.address", TestRequest(value="test"))
    assert "returned an invalid type" in str(exc_info.value)
