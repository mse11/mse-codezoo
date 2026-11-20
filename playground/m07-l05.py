# a function that gives back an answer
def count_to_wall():
    n = 0
    while not is_blocked():
        step(1)
        n += 1
    return n


say(count_to_wall())
