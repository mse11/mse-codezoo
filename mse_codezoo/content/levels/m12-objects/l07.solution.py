class Counter:
    def __init__(self):
        self.n = 0

    def add(self):
        self.n += 1

c = Counter()
c.add()
c.add()
say(c.n)
