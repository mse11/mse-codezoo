def route():
    yield 2
    yield 3

for hop in route():
    fly(hop)
    grab()
