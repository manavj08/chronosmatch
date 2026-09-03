class RingBuffer:
    """
    Fixed-size circular buffer for storing recent orders.
    """

    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = [None] * capacity
        self.start = 0
        self.count = 0

    def add(self, item):

        if self.count < self.capacity:
            index = (self.start + self.count) % self.capacity
            self.buffer[index] = item
            self.count += 1
        else:
            # Overwrite oldest item
            self.buffer[self.start] = item
            self.start = (self.start + 1) % self.capacity

    def get_recent(self, n):
        """
        Return most recent items.
        Newest item comes first.
        """

        n = min(n, self.count)

        result = []

        for i in range(n):
            index = (self.start + self.count - 1 - i) % self.capacity
            result.append(self.buffer[index])

        return result

    def get_all(self):
        """
        Return all items.
        """

        result = []

        for i in range(self.count):
            index = (self.start + i) % self.capacity
            result.append(self.buffer[index])

        return result

    def __len__(self):
        return self.count