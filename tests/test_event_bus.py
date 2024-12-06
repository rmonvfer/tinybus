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
import uuid

from typing import Optional
from pydantic import BaseModel
from fixtures import TestRequest, TestResponse

from tinybus.models import DeliveryOptions, Message
from tinybus.exceptions import HandlerAlreadyRegisteredError, HandlerNotFoundError, EventBusError


# Additional test models
class InvalidRequest(BaseModel):
    invalid_field: dict  # Will cause validation error


class ChainedResponse(BaseModel):
    value: str
    next_address: Optional[str] = None


@pytest.mark.asyncio
async def test_consumer_registration(event_bus):
    """Test registering and unregistering consumers"""

    async def handler(msg: Message[TestRequest]) -> TestResponse:
        return TestResponse(result=f"Processed: {msg.body.value}")

    # Register consumer
    consumer = event_bus.consumer("test.address", handler)
    assert "test.address" in event_bus.get_consumers()

    # Try registering duplicate
    with pytest.raises(HandlerAlreadyRegisteredError):
        event_bus.consumer("test.address", handler)

    # Unregister consumer
    consumer.unregister()
    assert "test.address" not in event_bus.get_consumers()


@pytest.mark.asyncio
async def test_request_response(event_bus):
    """Test request-response pattern"""

    async def handler(msg: Message[TestRequest]) -> TestResponse:
        return TestResponse(result=f"Processed: {msg.body.value}")

    event_bus.consumer("test.address", handler)

    # Test successful request
    request = TestRequest(value="hello")
    response = await event_bus.request("test.address", request)
    assert response.result == "Processed: hello"

    # Test request to non-existent address
    with pytest.raises(HandlerNotFoundError):
        await event_bus.request("non.existent", request)

    # Test timeout
    async def slow_handler(msg: Message[TestRequest]) -> TestResponse:
        await asyncio.sleep(2)
        return TestResponse(result="too late")

    event_bus.consumer("slow.address", slow_handler)
    with pytest.raises(EventBusError) as exc_info:
        await event_bus.request("slow.address", request, options=DeliveryOptions(timeout=0.1))
    assert "timed out" in str(exc_info.value)

    # Test handler error
    async def error_handler(msg: Message[TestRequest]) -> TestResponse:
        raise ValueError("Something went wrong")

    event_bus.consumer("error.address", error_handler)
    with pytest.raises(EventBusError) as exc_info:
        await event_bus.request("error.address", request)
    assert "Something went wrong" in str(exc_info.value)


@pytest.mark.asyncio
async def test_publish_subscribe(event_bus):
    """Test publish-subscribe pattern"""
    received_events = []

    async def listener1(event):
        received_events.append(("listener1", event))

    async def listener2(event):
        received_events.append(("listener2", event))

    # Register listeners
    listener = event_bus.on("test.event", listener1)
    event_bus.on("test.event")(listener2)

    # Test event publishing
    test_event = TestRequest(value="event data")
    await event_bus.publish("test.event", test_event)

    assert len(received_events) == 2
    assert received_events[0] == ("listener1", test_event)
    assert received_events[1] == ("listener2", test_event)

    # Test listener removal
    listener.unregister()
    received_events.clear()

    await event_bus.publish("test.event", test_event)
    assert len(received_events) == 1
    assert received_events[0] == ("listener2", test_event)


@pytest.mark.asyncio
async def test_event_bus_utilities(event_bus):
    """Test utility methods of EventBus"""

    async def handler(msg):
        pass

    async def event_handler(event):
        pass

    # Test get_consumers
    consumer = event_bus.consumer("test.address", handler)
    assert event_bus.get_consumers() == ["test.address"]

    # Test get_listeners
    listener = event_bus.on("test.event", event_handler)
    assert len(event_bus.get_listeners("test.event")) == 1
    assert event_bus.get_listeners("test.event")[0] == event_handler

    # Test removing non-existent listener (should not raise)
    event_bus.remove_listener("non.existent", event_handler)

    # Clean up
    consumer.unregister()
    listener.unregister()
    assert len(event_bus.get_consumers()) == 0
    assert len(event_bus.get_listeners("test.event")) == 0


@pytest.mark.asyncio
async def test_message_validation(event_bus):
    """Test message validation and edge cases"""

    # Test null message
    async def null_handler(msg: Message[None]) -> str:
        return "Processed null message"

    event_bus.consumer("null.address", null_handler)
    response = await event_bus.request("null.address", None)
    assert response == "Processed null message"

    # Test message ID uniqueness
    messages = set()
    for _ in range(100):
        msg = Message[str](body="test", id=str(uuid.uuid4()))
        messages.add(msg.id)
    assert len(messages) == 100


@pytest.mark.asyncio
async def test_error_handling(event_bus):
    """Test various error conditions"""
    received = []
    errors = []

    # Test listener exception handling
    @event_bus.on("error.event")
    async def failing_listener(msg):
        try:
            raise ValueError("Listener failed")
        except Exception as e:
            errors.append(str(e))

    @event_bus.on("error.event")
    async def working_listener(msg):
        received.append(msg)

    # Should not affect working listener
    await event_bus.publish("error.event", "test")
    assert len(received) == 1
    assert len(errors) == 1
    assert "Listener failed" in errors[0]

    # Test concurrent timeouts
    async def slow_handler(msg: Message[str]) -> str:
        await asyncio.sleep(1)
        return "too late"

    event_bus.consumer("slow.address", slow_handler)

    # Launch multiple concurrent requests
    options = DeliveryOptions(timeout=0.1)
    tasks = []
    for _ in range(3):
        task = event_bus.request("slow.address", "test", options=options)
        tasks.append(task)

    try:
        await asyncio.gather(*tasks)
    except EventBusError:
        pass  # Expected timeout error
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")
    else:
        pytest.fail("Expected EventBusError was not raised")


@pytest.mark.asyncio
async def test_performance_edges(event_bus):
    """Test performance edge cases"""
    # Test many listeners
    received = []
    for i in range(100):
        async def listener(msg, i=i):
            received.append(i)

        event_bus.on("many.listeners", listener)

    await event_bus.publish("many.listeners", "test")
    assert len(received) == 100

    # Test high frequency publishing
    counter = 0

    @event_bus.on("high.frequency")
    async def count_events(msg):
        nonlocal counter
        counter += 1

    # Publish many events rapidly
    await asyncio.gather(*[
        event_bus.publish("high.frequency", i)
        for i in range(100)
    ])
    assert counter == 100


@pytest.mark.asyncio
async def test_advanced_patterns(event_bus):
    """Test advanced messaging patterns"""

    # Test request-response chaining
    async def first_handler(msg: Message[str]) -> ChainedResponse:
        return ChainedResponse(
            value=f"First: {msg.body}",
            next_address="second.handler"
        )

    async def second_handler(msg: Message[ChainedResponse]) -> str:
        return f"Second: {msg.body.value}"

    event_bus.consumer("first.handler", first_handler)
    event_bus.consumer("second.handler", second_handler)

    # Chain requests based on response
    first_response = await event_bus.request("first.handler", "test")
    if first_response.next_address:
        final_response = await event_bus.request(
            first_response.next_address,
            first_response
        )
        assert final_response == "Second: First: test"

    # Test conditional message handling
    async def conditional_handler(msg: Message[TestRequest]) -> Optional[TestResponse]:
        if msg.body.value == "skip":
            return None
        return TestResponse(result=f"Processed: {msg.body.value}")

    event_bus.consumer("conditional.address", conditional_handler)

    response = await event_bus.request(
        "conditional.address",
        TestRequest(value="process")
    )
    assert response.result == "Processed: process"

    response = await event_bus.request(
        "conditional.address",
        TestRequest(value="skip")
    )
    assert response is None
