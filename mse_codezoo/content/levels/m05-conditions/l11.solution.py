bananas = 0
for i in range(5):
    step(1)
    if item_here() == "banana":
        grab()
        bananas += 1
    elif item_here() == "coconut":
        grab()
say(f"{bananas} bananas")
