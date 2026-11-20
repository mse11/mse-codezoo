def safe_step(n):
    if n < 0:
        raise ValueError("no walking backwards")
    step(n)


for n in [1, -2, 2]:
    try:
        safe_step(n)
        grab()
    except ValueError as e:
        say(e)
