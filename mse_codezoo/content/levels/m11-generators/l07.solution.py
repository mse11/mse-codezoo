def flowers():
    n = 0
    while True:
        n += 1
        yield n

def nectar(source):
    for flower in source:
        if flower % 3 == 0:
            yield flower * 2

drops = nectar(flowers())
for _ in range(3):
    say(next(drops))
