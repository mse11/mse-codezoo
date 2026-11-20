def sneak():
    if is_blocked():
        grab()
        return
    if guard_ahead():
        hide()
    step(1)
    sneak()


sneak()
