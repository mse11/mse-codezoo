here = 0
for spot in (x for x in range(1, 9) if x % 3 == 0):
    step(spot - here)
    grab()
    here = spot
say(f"{here} steps")
