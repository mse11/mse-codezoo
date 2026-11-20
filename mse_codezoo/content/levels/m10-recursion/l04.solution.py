def count():
    if not item_ahead():
        return 0
    step(1)
    grab()
    return 1 + count()


say(count())
