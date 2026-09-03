from shared.ring_buffer import RingBuffer


def test_write_and_read():
    rb = RingBuffer(capacity=4, create=True)
    order = {'order_id': 1, 'side': 'B', 'price': 100.5, 'quantity': 50, 'timestamp': 171000000}
    rb.write_order(order)
    result = rb.read_order()
    assert result == order


def test_empty_buffer_is_empty():
    rb = RingBuffer(capacity=4, create=True)
    assert rb.is_empty() is True


def test_full_buffer():
    rb = RingBuffer(capacity=2, create=True)
    order = {'order_id': 1, 'side': 'B', 'price': 100.5, 'quantity': 50, 'timestamp': 171000000}
    rb.write_order(order)
    rb.write_order(order)
    assert rb.is_full() is True
    assert rb.write_order(order) is False


def test_wraparound():
    rb = RingBuffer(capacity=2, create=True)
    order = {'order_id': 1, 'side': 'B', 'price': 100.5, 'quantity': 50, 'timestamp': 171000000}
    rb.write_order(order)
    rb.read_order()
    rb.write_order(order)
    rb.read_order()
    assert rb.get_stats()['write_pointer'] == 0
    assert rb.get_stats()['read_pointer'] == 0


def test_multiple_writes():
    rb = RingBuffer(capacity=4, create=True)
    orders = [
        {'order_id': 1, 'side': 'B', 'price': 100.0, 'quantity': 10, 'timestamp': 1},
        {'order_id': 2, 'side': 'S', 'price': 101.0, 'quantity': 20, 'timestamp': 2},
        {'order_id': 3, 'side': 'B', 'price': 102.0, 'quantity': 30, 'timestamp': 3},
    ]
    for o in orders:
        assert rb.write_order(o) is True

    assert rb.size() == 3

    for o in orders:
        assert rb.read_order() == o

    assert rb.is_empty() is True