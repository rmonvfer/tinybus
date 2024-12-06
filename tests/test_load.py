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
import time

from typing import List
from dataclasses import dataclass
from fixtures import TestRequest, TestResponse


@dataclass
class LoadTestMetrics:
    total_time: float
    requests_per_second: float
    success_count: int
    error_count: int
    avg_response_time: float


async def measure_request_latency(event_bus, request: TestRequest) -> float:
    start = time.perf_counter()
    await event_bus.request("test.address", request)
    return time.perf_counter() - start


@pytest.mark.asyncio
async def test_request_response_load(event_bus):
    """Test request-response pattern under load"""

    # Setup handler
    async def handler(msg):
        await asyncio.sleep(0.001)  # Simulate some work
        return TestResponse(result=f"Processed: {msg.body.value}")

    event_bus.consumer("test.address", handler)

    # Test parameters
    num_requests = 1000
    concurrent_requests = 100

    # Create requests
    requests = [TestRequest(value=f"request_{i}") for i in range(num_requests)]
    latencies: List[float] = []
    errors = 0

    start_time = time.perf_counter()

    # Process requests in batches
    for i in range(0, num_requests, concurrent_requests):
        batch = requests[i:i + concurrent_requests]
        tasks = [measure_request_latency(event_bus, req) for req in batch]
        batch_latencies = await asyncio.gather(*tasks, return_exceptions=True)

        for latency in batch_latencies:
            if isinstance(latency, Exception):
                errors += 1
            else:
                latencies.append(latency)

    total_time = time.perf_counter() - start_time

    metrics = LoadTestMetrics(
        total_time=total_time,
        requests_per_second=num_requests / total_time,
        success_count=len(latencies),
        error_count=errors,
        avg_response_time=sum(latencies) / len(latencies) if latencies else 0
    )

    print(f"\nRequest-Response Load Test Results:")
    print(f"Total time: {metrics.total_time:.2f}s")
    print(f"Requests/second: {metrics.requests_per_second:.2f}")
    print(f"Success rate: {(metrics.success_count / num_requests) * 100:.1f}%")
    print(f"Average response time: {metrics.avg_response_time * 1000:.2f}ms")

    assert metrics.error_count == 0
    assert metrics.requests_per_second > 100  # Should handle at least 100 req/s
    assert metrics.avg_response_time < 0.1  # Average response under 100ms


@pytest.mark.asyncio
async def test_publish_subscribe_load(event_bus):
    """Test publish-subscribe pattern under load"""
    received_count = 0
    listener_count = 50
    message_count = 1000

    # Register multiple listeners
    async def listener(msg):
        nonlocal received_count
        await asyncio.sleep(0.001)  # Simulate work
        received_count += 1

    for _ in range(listener_count):
        event_bus.on("test.event", listener)

    start_time = time.perf_counter()

    # Publish messages in parallel
    publish_tasks = [
        event_bus.publish("test.event", TestRequest(value=f"event_{i}"))
        for i in range(message_count)
    ]
    await asyncio.gather(*publish_tasks)

    total_time = time.perf_counter() - start_time
    expected_total = message_count * listener_count

    metrics = LoadTestMetrics(
        total_time=total_time,
        requests_per_second=message_count / total_time,
        success_count=received_count,
        error_count=expected_total - received_count,
        avg_response_time=total_time / message_count
    )

    print(f"\nPublish-Subscribe Load Test Results:")
    print(f"Total time: {metrics.total_time:.2f}s")
    print(f"Messages/second: {metrics.requests_per_second:.2f}")
    print(f"Total events processed: {metrics.success_count}")
    print(f"Average processing time per message: {metrics.avg_response_time * 1000:.2f}ms")

    assert metrics.error_count == 0
    assert metrics.success_count == expected_total
    assert metrics.requests_per_second > 50  # Should handle at least 50 msg/s


@pytest.mark.asyncio
async def test_mixed_load(event_bus):
    """Test both patterns simultaneously under load"""
    received_events = 0
    processed_requests = 0

    # Setup request handler
    async def request_handler(msg):
        nonlocal processed_requests
        await asyncio.sleep(0.001)
        processed_requests += 1
        return TestResponse(result=f"Processed: {msg.body.value}")

    # Setup event listener
    async def event_listener(msg):
        nonlocal received_events
        await asyncio.sleep(0.001)
        received_events += 1

    event_bus.consumer("test.address", request_handler)
    for _ in range(10):  # 10 listeners
        event_bus.on("test.event", event_listener)

    # Test parameters
    num_requests = 500
    num_events = 500

    start_time = time.perf_counter()

    # Mix request-response and publish-subscribe
    request_tasks = [
        event_bus.request("test.address", TestRequest(value=f"req_{i}"))
        for i in range(num_requests)
    ]

    publish_tasks = [
        event_bus.publish("test.event", TestRequest(value=f"event_{i}"))
        for i in range(num_events)
    ]

    # Run everything concurrently
    await asyncio.gather(*(request_tasks + publish_tasks))

    total_time = time.perf_counter() - start_time
    expected_events = num_events * 10  # 10 listeners

    print(f"\nMixed Load Test Results:")
    print(f"Total time: {total_time:.2f}s")
    print(f"Total throughput: {(num_requests + num_events) / total_time:.2f} ops/s")
    print(f"Requests processed: {processed_requests}")
    print(f"Events processed: {received_events}")

    assert processed_requests == num_requests
    assert received_events == expected_events
