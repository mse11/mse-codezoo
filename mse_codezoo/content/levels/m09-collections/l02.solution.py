found = []
for i in range(5):
    step(1)
    if item_here():
        found.append(item_here())
        grab()
say(len(found))
