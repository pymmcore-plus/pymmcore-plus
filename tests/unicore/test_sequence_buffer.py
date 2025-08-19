"""Test suite for the SequenceBuffer class."""

import threading
import time

import numpy as np
import pytest

from pymmcore_plus.experimental.unicore.core._sequence_buffer import SequenceBuffer


@pytest.fixture
def small_buffer() -> SequenceBuffer:
    """Create a small buffer for testing."""
    return SequenceBuffer(size_mb=1.0, overwrite_on_overflow=True)


@pytest.fixture
def no_overwrite_buffer() -> SequenceBuffer:
    """Create a buffer that doesn't overwrite on overflow."""
    return SequenceBuffer(size_mb=1.0, overwrite_on_overflow=False)


@pytest.fixture
def sample_data() -> dict:
    """Create sample numpy arrays for testing."""
    return {
        "small": np.random.randint(0, 255, (10, 10), dtype=np.uint8),
        "medium": np.random.randint(0, 255, (100, 100), dtype=np.uint8),
        "large": np.random.randint(0, 255, (500, 500), dtype=np.uint8),
        "float": np.random.random((50, 50)).astype(np.float32),
        "int32": np.random.randint(0, 1000, (20, 20), dtype=np.int32),
    }


@pytest.fixture
def sample_metadata() -> dict:
    """Create sample metadata for testing."""
    return {
        "timestamp": 123456789.0,
        "camera_id": "cam_01",
        "exposure": 100.0,
        "gain": 1.5,
        "temperature": 25.3,
    }


def test_buffer_initialization() -> None:
    """Test buffer initialization with different parameters."""
    # Test default parameters
    buffer = SequenceBuffer(size_mb=2.0)
    assert buffer.size_mb == 2.0
    assert buffer.size_bytes == 2 * 1024 * 1024
    assert buffer.overwrite_on_overflow is True
    assert buffer.used_bytes == 0
    assert buffer.free_bytes == buffer.size_bytes
    assert len(buffer) == 0
    assert not buffer.overflow_occurred

    # Test with overwrite disabled
    buffer = SequenceBuffer(size_mb=1.5, overwrite_on_overflow=False)
    assert buffer.size_mb == 1.5
    assert buffer.overwrite_on_overflow is False


def test_buffer_properties(small_buffer: SequenceBuffer) -> None:
    """Test buffer property calculations."""
    assert small_buffer.size_mb == 1.0
    assert small_buffer.size_bytes == 1024 * 1024
    assert small_buffer.free_mb == 1.0
    assert small_buffer.used_bytes == 0
    assert small_buffer.free_bytes == 1024 * 1024


def test_acquire_write_slot_basic(small_buffer: SequenceBuffer) -> None:
    """Test basic write slot acquisition."""
    shape = (100, 100)
    array = small_buffer.acquire_slot(shape, dtype=np.uint8)

    assert array.shape == shape
    assert array.dtype == np.uint8
    assert array.size == 10000

    # Array should be writable
    array[0, 0] = 255
    assert array[0, 0] == 255


def test_acquire_write_slot_different_dtypes(small_buffer: SequenceBuffer) -> None:
    """Test write slot acquisition with different data types."""
    # Test uint8
    array_uint8 = small_buffer.acquire_slot((10, 10), dtype=np.uint8)
    small_buffer.finalize_slot()
    assert array_uint8.dtype == np.uint8

    # Test float32
    array_float32 = small_buffer.acquire_slot((10, 10), dtype=np.float32)
    small_buffer.finalize_slot()
    assert array_float32.dtype == np.float32

    # Test int32
    array_int32 = small_buffer.acquire_slot((10, 10), dtype=np.int32)
    small_buffer.finalize_slot()
    assert array_int32.dtype == np.int32


def test_acquire_write_slot_too_large(small_buffer: SequenceBuffer) -> None:
    """Test that requesting too large a slot raises an error."""
    # Try to allocate more than the buffer can hold
    huge_shape = (2000, 2000)  # Much larger than 1MB buffer

    with pytest.raises(BufferError, match="exceeds buffer capacity"):
        small_buffer.acquire_slot(huge_shape, dtype=np.uint8)


def test_finalize_write_slot(
    small_buffer: SequenceBuffer, sample_metadata: dict
) -> None:
    """Test finalizing write slots."""
    array = small_buffer.acquire_slot((50, 50))
    array.fill(42)

    # Finalize without metadata
    small_buffer.finalize_slot()
    assert len(small_buffer) == 1

    # Test with metadata
    array2 = small_buffer.acquire_slot((30, 30))
    array2.fill(100)
    small_buffer.finalize_slot(sample_metadata)
    assert len(small_buffer) == 2


def test_finalize_invalid_array(small_buffer: SequenceBuffer) -> None:
    """Test finalizing an array that wasn't acquired from the buffer."""

    with pytest.raises(RuntimeError, match="No pending slot to finalize"):
        small_buffer.finalize_slot()


def test_insert_data_basic(
    small_buffer: SequenceBuffer, sample_data: dict, sample_metadata: dict
) -> None:
    """Test basic data insertion."""
    data = sample_data["small"]
    small_buffer.insert_data(data, sample_metadata)

    assert len(small_buffer) == 1
    assert small_buffer.used_bytes > 0

    # Retrieve and verify
    result = small_buffer.pop_next()
    assert result is not None
    retrieved_data, retrieved_metadata = result

    np.testing.assert_array_equal(retrieved_data, data)
    assert retrieved_metadata == sample_metadata


def test_insert_data_without_metadata(
    small_buffer: SequenceBuffer, sample_data: dict
) -> None:
    """Test data insertion without metadata."""
    data = sample_data["medium"]
    small_buffer.insert_data(data)

    assert len(small_buffer) == 1

    result = small_buffer.pop_next()
    assert result is not None
    retrieved_data, retrieved_metadata = result

    np.testing.assert_array_equal(retrieved_data, data)
    assert isinstance(retrieved_metadata, dict)


def test_pop_next_fifo_order(small_buffer: SequenceBuffer, sample_data: dict) -> None:
    """Test that pop_next follows FIFO order."""
    data1 = sample_data["small"]
    data2 = sample_data["medium"]

    # Insert data in order
    small_buffer.insert_data(data1, {"order": 1})
    small_buffer.insert_data(data2, {"order": 2})

    # Pop should return in FIFO order
    result1 = small_buffer.pop_next()
    assert result1 is not None
    _, metadata1 = result1
    assert metadata1["order"] == 1

    result2 = small_buffer.pop_next()
    assert result2 is not None
    _, metadata2 = result2
    assert metadata2["order"] == 2

    # Buffer should be empty now
    assert small_buffer.pop_next() is None


def test_pop_next_empty_buffer(small_buffer: SequenceBuffer) -> None:
    """Test popping from empty buffer."""
    assert small_buffer.pop_next() is None


def test_peek_last(small_buffer: SequenceBuffer, sample_data: dict) -> None:
    """Test peeking at the most recent data."""
    # Empty buffer
    assert small_buffer.peek_last() is None

    # Add some data
    data1 = sample_data["small"]
    data2 = sample_data["medium"]

    small_buffer.insert_data(data1, {"id": 1})
    result = small_buffer.peek_last()
    assert result is not None
    _, metadata = result
    assert metadata["id"] == 1

    # Add another item
    small_buffer.insert_data(data2, {"id": 2})
    result = small_buffer.peek_last()
    assert result is not None
    _, metadata = result
    assert metadata["id"] == 2

    # Buffer should still have both items
    assert len(small_buffer) == 2


def test_peek_nth(small_buffer: SequenceBuffer) -> None:
    """Test peeking at nth data entry."""
    # Empty buffer
    assert small_buffer.peek_nth_from_last(0) is None
    assert small_buffer.peek_nth_from_last(-1) is None

    # Add test data
    for i in range(3):
        data = np.full((10, 10), i, dtype=np.uint8)
        small_buffer.insert_data(data, {"index": i})

    assert len(small_buffer) == 3

    # Peek at the last item
    result = small_buffer.peek_nth_from_last(0)
    assert result is not None
    _, metadata = result
    assert metadata["index"] == 2

    # Peek at the second last item
    result = small_buffer.peek_nth_from_last(1)
    assert result is not None
    _, metadata = result
    assert metadata["index"] == 1

    result = small_buffer.peek_nth_from_last(10)
    assert result is None  # Out of bounds


def test_clear_buffer(small_buffer: SequenceBuffer, sample_data: dict) -> None:
    """Test clearing the buffer."""
    # Add some data
    small_buffer.insert_data(sample_data["small"])
    small_buffer.insert_data(sample_data["medium"])

    assert len(small_buffer) == 2
    assert small_buffer.used_bytes > 0

    # Clear the buffer
    small_buffer.clear()

    assert len(small_buffer) == 0
    assert small_buffer.used_bytes == 0
    assert small_buffer.free_bytes == small_buffer.size_bytes
    assert not small_buffer.overflow_occurred
    assert small_buffer.peek_last() is None


def test_overflow_with_overwrite() -> None:
    """Test buffer overflow behavior when overwrite is enabled."""
    small_buffer = SequenceBuffer(size_mb=1.0, overwrite_on_overflow=True)

    large_data = np.random.randint(0, 255, (600, 600), dtype=np.uint8)  # ~360KB
    assert large_data.nbytes == 360000  # ~360KB

    # Fill buffer to near capacity
    small_buffer.insert_data(large_data, {"id": 1})
    small_buffer.insert_data(large_data, {"id": 2})
    small_buffer.insert_data(large_data, {"id": 3})  # This should fit

    # This should cause overflow and remove the oldest items
    small_buffer.insert_data(large_data, {"id": 4})
    assert small_buffer.overflow_occurred

    # The remaining data should be the newer ones
    result = small_buffer.peek_last()
    assert result is not None
    _, metadata = result
    assert metadata["id"] == 4


def test_overflow_without_overwrite(no_overwrite_buffer: SequenceBuffer) -> None:
    """Test buffer overflow behavior when overwrite is disabled."""
    large_data = np.random.randint(0, 255, (600, 600), dtype=np.uint8)  # ~360KB

    # Fill the buffer to near capacity
    no_overwrite_buffer.insert_data(large_data, {"id": 1})
    no_overwrite_buffer.insert_data(large_data, {"id": 2})

    # This should raise an error since we're at capacity and can't overwrite
    with pytest.raises(BufferError, match="Buffer is full and overwrite is disabled"):
        no_overwrite_buffer.insert_data(large_data, {"id": 3})


def test_overwrite_mode_property(small_buffer: SequenceBuffer) -> None:
    """Test getting and setting the overwrite mode."""
    assert small_buffer.overwrite_on_overflow is True

    # Should be able to change when empty
    small_buffer.overwrite_on_overflow = False
    assert small_buffer.overwrite_on_overflow is False

    # Add some data
    small_buffer.insert_data(np.zeros((10, 10)), {"test": True})

    # Should not be able to change when buffer has data
    with pytest.raises(
        RuntimeError, match="Cannot change overflow policy with active data in buffer"
    ):
        small_buffer.overwrite_on_overflow = True


def test_repr(small_buffer: SequenceBuffer, sample_data: dict) -> None:
    """Test string representation of the buffer."""
    repr_str = repr(small_buffer)
    assert "size_mb=1.0" in repr_str
    assert "slots=0" in repr_str
    assert "overwrite=True" in repr_str

    # Add some data and test again
    small_buffer.insert_data(sample_data["small"])
    repr_str = repr(small_buffer)
    assert "slots=1" in repr_str
    assert "used_mb=" in repr_str


def test_concurrent_access() -> None:
    """Test thread safety of the buffer."""
    buffer = SequenceBuffer(size_mb=2.0)
    errors = []
    num_producers = 3
    items_per_producer = 5

    def worker(thread_id: int) -> None:
        try:
            for i in range(items_per_producer):
                data = np.full((20, 20), thread_id * 100 + i, dtype=np.uint8)
                buffer.insert_data(data, {"thread": thread_id, "seq": i})
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    # Start and wait for producer threads
    threads = []
    for i in range(num_producers):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    # Wait for all threads to complete with timeout
    for t in threads:
        t.join(timeout=5.0)
        if t.is_alive():
            errors.append(Exception("Thread timed out"))

    # Check for errors
    assert len(errors) == 0, f"Errors occurred: {errors}"

    # Should have some data in buffer (exact count may vary due to overflow)
    assert len(buffer) > 0, "Buffer should contain some data after concurrent access"

    # Verify we can retrieve data without errors
    retrieved_count = 0
    while buffer.pop_next() is not None and retrieved_count < 20:
        retrieved_count += 1

    assert retrieved_count > 0, "Should be able to retrieve some data"


def _producer_worker(buffer: SequenceBuffer, thread_id: int, errors: list[str]) -> None:
    """Helper function for producer threads."""
    try:
        for i in range(3):
            data = np.full((15, 15), thread_id * 10 + i, dtype=np.uint8)
            buffer.insert_data(data, {"producer": thread_id, "item": i})
            time.sleep(0.002)
    except Exception as e:
        errors.append(f"Producer {thread_id}: {e}")


def _consumer_worker(
    buffer: SequenceBuffer,
    results: list[tuple],
    producers_done: threading.Event,
    expected_items: int,
    errors: list[str],
) -> None:
    """Helper function for consumer thread."""
    try:
        while len(results) < expected_items:
            result = buffer.pop_next()
            if result is not None:
                results.append(result)
                continue

            if producers_done.is_set():
                break

            time.sleep(0.001)
    except Exception as e:
        errors.append(f"Consumer: {e}")


def test_concurrent_producers_and_consumer() -> None:
    """Test concurrent producers with a single consumer."""
    buffer = SequenceBuffer(size_mb=2.0)
    errors: list[str] = []
    results: list[tuple] = []
    producers_done = threading.Event()
    expected_items = 6  # 2 producers x 3 items each

    # Start producer threads
    producer_threads = []
    for i in range(2):
        t = threading.Thread(target=_producer_worker, args=(buffer, i, errors))
        producer_threads.append(t)
        t.start()

    # Start consumer thread
    consumer_thread = threading.Thread(
        target=_consumer_worker,
        args=(buffer, results, producers_done, expected_items, errors),
    )
    consumer_thread.start()

    # Wait for producers to finish
    for t in producer_threads:
        t.join(timeout=3.0)

    # Signal that producers are done
    producers_done.set()

    # Wait for consumer to finish
    consumer_thread.join(timeout=3.0)

    # Check results
    assert len(errors) == 0, f"Errors occurred: {errors}"
    assert len(results) == expected_items


def test_memory_efficiency() -> None:
    """Test that the buffer efficiently manages memory."""
    buffer = SequenceBuffer(size_mb=1.0)

    # Create arrays that fit in the buffer pool
    small_arrays = []
    for i in range(10):
        array = buffer.acquire_slot((100, 100), dtype=np.uint8)
        array.fill(i)
        small_arrays.append(array)
        buffer.finalize_slot({"index": i})

    assert len(buffer) == 10

    # Check that data is correctly stored and retrievable
    for i in range(10):
        result = buffer.pop_next()
        assert result is not None
        data, metadata = result
        assert metadata["index"] == i
        assert np.all(data == i)


def test_zero_copy_workflow() -> None:
    """Test the zero-copy workflow with acquire/finalize."""
    buffer = SequenceBuffer(size_mb=1.0)

    # Acquire write slot
    array = buffer.acquire_slot((200, 200), dtype=np.uint8)

    # Write data directly to the array (simulating camera capture)
    test_pattern = np.arange(200 * 200, dtype=np.uint8).reshape(200, 200)
    array[:] = test_pattern

    # Finalize with metadata
    metadata = {"timestamp": 123456, "exposure": 100}
    buffer.finalize_slot(metadata)

    # Retrieve and verify
    result = buffer.pop_next()
    assert result is not None
    retrieved_data, retrieved_metadata = result

    np.testing.assert_array_equal(retrieved_data, test_pattern)
    assert retrieved_metadata["timestamp"] == 123456
    assert retrieved_metadata["exposure"] == 100


def test_mixed_data_types(small_buffer: SequenceBuffer) -> None:
    """Test buffer with mixed data types and shapes."""
    # Add various data types
    uint8_data = np.random.randint(0, 255, (50, 50), dtype=np.uint8)
    float32_data = np.random.random((30, 40)).astype(np.float32)
    int16_data = np.random.randint(-1000, 1000, (25, 25), dtype=np.int16)

    small_buffer.insert_data(uint8_data, {"type": "uint8"})
    small_buffer.insert_data(float32_data, {"type": "float32"})
    small_buffer.insert_data(int16_data, {"type": "int16"})

    assert len(small_buffer) == 3

    # Retrieve in FIFO order and verify types
    result1 = small_buffer.pop_next()
    assert result1 is not None
    data1, meta1 = result1
    assert data1.dtype == np.uint8
    assert meta1["type"] == "uint8"

    result2 = small_buffer.pop_next()
    assert result2 is not None
    data2, meta2 = result2
    assert data2.dtype == np.float32
    assert meta2["type"] == "float32"

    result3 = small_buffer.pop_next()
    assert result3 is not None
    data3, meta3 = result3
    assert data3.dtype == np.int16
    assert meta3["type"] == "int16"


def test_acquire_2slots_in_a_row() -> None:
    """Test acquiring slot when one is already pending."""
    buffer = SequenceBuffer(size_mb=1.0)

    # Acquire a slot but don't finalize it
    buffer.acquire_slot((10, 10))
    # acquire again
    buffer.acquire_slot((5, 5))

    # Finalize the first slot
    buffer.finalize_slot()
    # Finalize the second slot
    buffer.finalize_slot()

    # Now should be able to acquire a new slot
    buffer.acquire_slot((5, 5))
    buffer.finalize_slot()


# Additional tests to cover missing lines
def test_pop_into_buffer(small_buffer: SequenceBuffer) -> None:
    """Test pop_next with copy=True to cover line 173."""
    data = np.array([[1, 2], [3, 4]], dtype=np.uint8)
    out = np.empty_like(data)
    small_buffer.insert_data(data, {"test": True})

    result = small_buffer.pop_next(out=out)
    assert result is not None
    retrieved_data, metadata = result
    assert retrieved_data is out  # Should return the output buffer

    # Should be a copy, not a view
    assert retrieved_data.flags.owndata is True
    np.testing.assert_array_equal(retrieved_data, data)
    assert metadata["test"] is True
