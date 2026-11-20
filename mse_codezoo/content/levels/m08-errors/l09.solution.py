while not item_here():
    try:
        step(1)
    except CrackError:
        turn_left()
        step(1)
        turn_right()
        step(2)
        turn_right()
        step(1)
        turn_left()
catch()
