from burrow import back_up, turn_from, turn_to


def explore():
    grab()
    for side in sniff():
        turn_to(side)
        if guard_ahead():
            hide()
        step(1)
        explore()
        back_up()
        turn_from(side)


explore()
