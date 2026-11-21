def twice(move):
    def again():
        move()
        move()
    return again

def hop():
    step(1)

hop = twice(hop)
hop()
grab()
