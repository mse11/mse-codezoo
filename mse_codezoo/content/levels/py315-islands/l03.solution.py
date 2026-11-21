MISSING = sentinel("MISSING")
fish = {"Pip": 2.5, "Pop": None}
for chick in ["Pip", "Pop", "Pia"]:
    weight = fish.get(chick, MISSING)
    if weight is MISSING:
        say(f"{chick}: no fish yet")
    elif weight is None:
        say(f"{chick}: fish not weighed")
    else:
        say(f"{chick}: {weight} kg")
