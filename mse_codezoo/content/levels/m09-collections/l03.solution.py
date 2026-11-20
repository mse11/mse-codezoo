plan = [(2, "left"), (1, "right"), (2, "right"), (1, "left")]
for steps, turn in plan:
    step(steps)
    grab()
    if turn == "left":
        turn_left()
    else:
        turn_right()
