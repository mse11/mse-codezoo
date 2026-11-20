while True:
    grab()
    if not is_blocked():
        step(1)
    else:
        turn_right()
        if is_blocked():
            turn_left()
            turn_left()
            if is_blocked():
                break
