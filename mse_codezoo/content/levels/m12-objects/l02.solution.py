class Picker:
    def __init__(self, stride):
        self.stride = stride
        self.count = 0

    def pick(self):
        step(self.stride)
        grab()
        self.count += 1

p = Picker(3)
p.pick()
p.pick()
say(p.count)
