counts = {}
for i in range(5):
    step(1)
    kind = item_here()
    if kind:
        counts[kind] = counts.get(kind, 0) + 1
        grab()
say(counts["banana"])
