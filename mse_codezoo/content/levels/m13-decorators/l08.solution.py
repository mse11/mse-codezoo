class counted:
    def __init__(self, move):
        self.move = move
        self.calls = 0

    def __call__(self, *args):
        self.calls += 1
        self.move(*args)

@counted
def hop(n):
    step(n)

hop(1)
hop(2)
grab()
say(hop.calls)
