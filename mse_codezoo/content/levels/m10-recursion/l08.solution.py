def walk(n):
    if n == 0:
        return
    step(1)
    grab()
    walk(n - 1)


walk(3)
