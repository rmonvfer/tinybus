# 🚌 TinyBus

A modern, async-first Event Bus for Python 3.12+ inspired by Eclipse Vert.x. TinyBus provides a clean, type-safe way to implement event-driven architectures with both request-response and publish-subscribe patterns.

## Why
Because I've spent quite a lot of time evaluating event bus libraries but none seemed to support the async Request-Response pattern I needed. Some alternatives like [Ethereum's Lahja](https://github.com/ethereum/lahja) or [lightbus](https://github.com/adamcharnock/lightbus) seem too heavy and complex with lots of features I don't need (inter-process communication, queues, RPC...)

The Request-Response Events pattern is quite useful when growing an async backend with lots of internal messages being passed around (using the Actor [Model terminology](https://doc.akka.io/libraries/akka-core/current/typed/guide/actors-intro.html), method calls are considered messages) as it allows to decouple caller and callee very transparently and fits nicely in the asynchronous "mental model".

## Installation
```bash
uv add tinybus
```

## Quick Example

Here's a simple user service implementation showcasing TinyBus's main features

```python
import uuid

from enum import Enum
from typing import Optional

from pydantic import BaseModel
from tinybus import EventBus, Message

# First, we must define our addresses.
class Address(str, Enum):
    CREATE_USER = "create_user"
    GET_USER = "get_user"

# Then, the clases that hold the data being sent around
class User(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str

class CreateUserRequest(BaseModel):
    username: str
    email: str

class CreateUserResponse(BaseModel):
    user: User

class GetUserResponse(BaseModel):
    user: User

# This service is subscribed to all updates sent to the CREATE_USER and GET_USER
# addresses and will run the appropriate methods when a valid request is sent.
class UserService:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus

        # A fake data layer
        self._users: dict[uuid.UUID, User] = {}
        
        # Register handlers
        # If these methods are not used directly anywhere outside this class, you'll likely
        # want to make them private (self._create_user)
        self._event_bus.consumer(Address.CREATE_USER, self.create_user)
        self._event_bus.consumer(Address.GET_USER, self.get_user)
    
    async def create_user(self, message: Message[CreateUserRequest]) -> CreateUserResponse:
        # A Message is fairly simple, it has a header and a body.
        # Most of the time, you'll only be using the body because it contains the actual data you'll use.
        request = message.body

        # In the real world, you'll use a data layer to create your user (likely an async operation)
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            username=request.username,
            email=request.email
        )
        self.users[user_id] = user
        
        # We can also publish events without expecting a return value
        await self.event_bus.publish("user.created", user)

        # Return a response that will be received by the Address listener
        return CreateUserResponse(user=user)
    
    # Messages can hold any value, including builtins.
    async def get_user(self, message: Message[uuid.UUID]) -> Optional[GetUserResponse]:
        requested_user_id = message.body
        if found_user := self.users.get(user_id) is not None:
            return GetUserResponse(user=found_user)
        else:
            # You can return None too (no need to wrap it in a custom object)
            return None


async def main():
    # Create an event bus
    event_bus = EventBus()
    
    # Create service
    user_service = UserService(event_bus)
    
    # Register event listener
    @event_bus.on("user.created")
    async def on_user_created(user: User):
        print(f"User created: {user.username}")
    
    # Send a request to the handler for the CREATE_USER address
    response = await event_bus.request(
        Address.CREATE_USER,
        CreateUserRequest(username="john", email="john@example.com")
    )
    
    # Likewise, call the handler of the GET_USER address
    user = await event_bus.request(
        Address.GET_USER,
        response.id
    )
    
    print(f"Retrieved user: {user.username}")
```


## Key Concepts

### Request-Response Pattern

TinyBus implements an address-based messaging system where consumers register handlers for specific addresses. When a request is made to an address, the corresponding handler processes it and returns a response

```python
# Register the consumer for a given address.
# Addresses can be strings too although we recommend using Enums for readability
@event_bus.consumer("greeting")
async def handle_greeting(msg: Message[str]) -> str:
    return f"Hello, {msg.body}!"

# Send a request
response = await event_bus.request("greeting", "World")
print(response) # Prints: Hello, World!
```

### Publish-Subscribe Pattern

The event bus also supports event-based communication where multiple listeners can subscribe to events where you do not care about the result or what happens when it is delivered.

```python
# Register listeners using the .on annotation
@event_bus.on("user.created")
async def notify_admin(user: User):
    print(f"New user registered: {user.email}")

# or the .on method directly
async def send_welcome_email(user: User):
    print(f"Sending welcome email to {user.email}")
event_bus.on("user.created", send_welcome_email)

# Publish an event
await event_bus.publish("user.created", user)
# > "New user registered: john@example.com"
```


## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

## License

TinyBus is MIT licensed. See the [LICENSE](LICENSE) file for details.