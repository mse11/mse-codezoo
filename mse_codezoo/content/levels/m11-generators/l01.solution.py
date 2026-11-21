spots = [n for n in range(8) if n % 2 == 1]
here = 0
for spot in spots:
    step(spot - here)
    grab()
    here = spot
