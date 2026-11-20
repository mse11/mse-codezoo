score = 0


def grab_and_count():
    global score
    step(1)
    grab()
    score += 1


for i in range(4):
    grab_and_count()
say(score)
