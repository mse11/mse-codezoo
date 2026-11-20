while True:
    turn_left()
    if is_blocked():
        climb()
    turn_right()
    if is_blocked():
        break
    step(1)
