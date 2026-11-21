class Basket:
    def __init__(self):
        self.items = 0

    def add(self):
        grab()
        self.items += 1

    @property
    def full(self):
        return self.items >= 2

basket = Basket()
while not basket.full:
    step(1)
    if item_here():
        basket.add()
