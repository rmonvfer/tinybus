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

import asyncio

from typing import Any, Callable, Optional, TypeVar, get_type_hints, Generic
from collections import defaultdict
from pydantic import BaseModel

from .exceptions import (
    HandlerAlreadyRegisteredError,
    HandlerNotFoundError,
    HandlerExecutionError,
    HandlerTimeoutError
)
from .models import MessageHandler, EventHandler, DeliveryOptions, Message

T = TypeVar('T')  # Message body type
R = TypeVar('R')  # Response type


class Consumer(Generic[T, R]):
    """
    Represents a registered message consumer.

    Attributes:
        event_bus: The EventBus instance
        address: The address this consumer is registered to
        handler: The handler function
    """

    def __init__(self, event_bus: 'EventBus', address: str, handler: MessageHandler[T, R]):
        self.event_bus = event_bus
        self.address = address
        self.handler = handler

    def unregister(self) -> None:
        """Unregister this consumer from the event bus"""
        self.event_bus.remove_consumer(self.address)


class Listener:
    """
    Represents a registered event listener.

    Attributes:
        event_bus: The EventBus instance
        event: The event name this listener is registered to
        handler: The handler function
    """

    def __init__(self, event_bus: 'EventBus', event: str, handler: EventHandler):
        self.event_bus = event_bus
        self.event = event
        self.handler = handler

    def unregister(self) -> None:
        """Unregister this listener from the event bus"""
        self.event_bus.remove_listener(self.event, self.handler)


class EventBus:
    """
    An event bus implementation supporting both request-response and publish-subscribe patterns.

    Features:
    - Address-based message routing with responses (like Vert.x)
    - Event-based publish-subscribe
    - Async-first design
    - Type-safe message passing using Pydantic models
    """

    def __init__(self):
        self._consumers: dict[str, tuple[MessageHandler, Optional[type]]] = {}
        self._listeners: defaultdict[str, list[EventHandler]] = defaultdict(list)
        self._reply_futures: dict[str, asyncio.Future] = {}

    def consumer(
            self,
            address: str,
            handler: MessageHandler[T, R]
    ) -> Consumer[T, R]:
        """
        Register a message handler for a specific address.

        Args:
            address: The address to handle messages for
            handler: The async function that will handle messages

        Returns:
            A Consumer object that can be used to unregister the handler

        Raises:
            HandlerAlreadyRegisteredError: If a handler is already registered for this address
        """
        if address in self._consumers:
            raise HandlerAlreadyRegisteredError(f"Handler already registered for address: {address}")

        # Extract the return type from the handler's type hints
        handler_signature = get_type_hints(handler)
        expected_return_type = handler_signature.get('return', None)

        self._consumers[address] = (handler, expected_return_type)
        return Consumer(self, address, handler)

    def on(self, event: str, handler: Optional[EventHandler] = None) -> Callable[[EventHandler], Listener] | Listener:
        """
        Register an event listener. Can be used as a decorator or method.

        Args:
            event: The event name to listen for
            handler: The async function that will handle the event (optional when used as decorator)

        Returns:
            When used as decorator: A callable that returns a Listener
            When used as method: A Listener object
        """

        def decorator(handler_fn: EventHandler) -> Listener:
            self._listeners[event].append(handler_fn)
            return Listener(self, event, handler_fn)

        if handler is None:
            # Used as decorator: @event_bus.on("event.name")
            return decorator
        else:
            # Used as method: event_bus.on("event.name", handler_fn)
            return decorator(handler)

    async def request(
            self,
            address: str,
            message: Optional[Any] = None,
            options: Optional[DeliveryOptions] = None
    ) -> Any:
        """Send a message to an address and wait for a reply.

        Args:
            address: The target address
            message: The message payload (can be any type)
            options: Delivery configuration options

        Raises:
            HandlerNotFoundError: If no handler is registered for the address
            HandlerTimeoutError: If the handler execution times out
            HandlerExecutionError: If the handler fails during execution
            EventBusError: For other unexpected errors
        """
        if address not in self._consumers:
            raise HandlerNotFoundError(f"No handler registered for address: {address}")

        options = options or DeliveryOptions()
        handler, expected_return_type = self._consumers[address]
        msg = Message[Any].create(message)

        try:
            response = await asyncio.wait_for(
                handler(msg),
                timeout=options.timeout
            )
            if expected_return_type is not None and not isinstance(response, expected_return_type):
                raise TypeError(
                    f"Handler for address '{address}' returned an invalid type: "
                    f"expected '{expected_return_type.__name__}', got '{type(response).__name__}'"
                )
            return response
        except asyncio.TimeoutError:
            raise HandlerTimeoutError(address, options.timeout)
        except Exception as e:
            raise HandlerExecutionError(address, e)

    async def publish[T: BaseModel](self, event: str, message: T) -> None:
        """
        Publish an event to all registered listeners.

        Args:
            event: The event name
            message: The event payload
        """
        listeners = self._listeners[event]
        if listeners:
            # Wait for all listeners to complete
            await asyncio.gather(
                *(listener(message) for listener in listeners)
            )

    def remove_consumer(self, address: str) -> None:
        """
        Remove a consumer handler from the event bus.

        Args:
            address: The address of the consumer to remove
        """
        self._consumers.pop(address, None)

    def remove_listener(self, event: str, handler: EventHandler) -> None:
        """
        Remove an event listener from the event bus.

        Args:
            event: The event name
            handler: The handler to remove
        """
        if event in self._listeners:
            self._listeners[event].remove(handler)
            if not self._listeners[event]:
                del self._listeners[event]

    def get_consumers(self) -> list[str]:
        """
        Get a list of all registered consumer addresses.

        Returns:
            List of registered addresses
        """
        return list(self._consumers.keys())

    def get_listeners(self, event: str) -> list[EventHandler]:
        """
        Get all listeners registered for an event.

        Args:
            event: The event name

        Returns:
            List of handlers registered for the event
        """
        return self._listeners[event].copy()
