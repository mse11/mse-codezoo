count = 0
while item_ahead():
    step(1)
    grab()
    count += 1
say(count)
