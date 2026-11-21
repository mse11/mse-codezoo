jumps = iter([2, 2, 3])
while True:
    try:
        n = next(jumps)
    except StopIteration:
        break
    step(n)
    grab()
