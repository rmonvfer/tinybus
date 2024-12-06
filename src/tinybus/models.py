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

import uuid

from typing import TypeAlias, Callable, Any, Optional

from pydantic import BaseModel

type MessageT[T: BaseModel] = T
type ResponseT[R: BaseModel] = R

MessageHandler: TypeAlias = Callable[[MessageT], ResponseT | None]
EventHandler: TypeAlias = Callable[[Any], None]


class Message[T](BaseModel):
    """
    Represents a message in the event bus.

    Attributes:
        id: Unique identifier for the message
        body: The message payload
        reply_address: Optional address for replies
    """
    id: str = str(uuid.uuid4())
    body: Optional[T] = None
    reply_address: Optional[str] = None

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def create(cls, body: Optional[T] = None) -> "Message[T]":
        return cls(body=body)


class DeliveryOptions(BaseModel):
    """
    Configuration options for message delivery.

    Attributes:
        timeout: Maximum time to wait for a response in seconds
        retry_attempts: Number of retry attempts for failed deliveries
    """
    timeout: float = 30.0
    retry_attempts: int = 0

    model_config = {"arbitrary_types_allowed": True}
