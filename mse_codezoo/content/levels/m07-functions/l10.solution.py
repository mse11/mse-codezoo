def bananas_ahead():
    count = 0
    while item_ahead():
        step(1)
        grab()
        count += 1
    return count


say(bananas_ahead())
