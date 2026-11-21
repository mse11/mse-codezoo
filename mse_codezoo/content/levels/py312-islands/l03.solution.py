from itertools import batched

for jar in batched(range(1, 24), 6):
    say(len(jar))
