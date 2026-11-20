counts = {}
for i in range(4):
    step(1)
    kind = item_here()
    counts[kind] = counts.get(kind, 0) + 1
    grab()
say(counts["banana"])
