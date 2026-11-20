while not item_here():
    if is_blocked():
        turn_right()
    else:
        step(1)
grab()
