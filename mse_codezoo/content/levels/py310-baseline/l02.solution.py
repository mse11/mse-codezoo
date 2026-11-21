chicks = ["Pip", "Pop", "Pia"]
fish = [2, 1, 3]
for chick, count in zip(chicks, fish, strict=True):
    say(f"{chick}: {count}")
