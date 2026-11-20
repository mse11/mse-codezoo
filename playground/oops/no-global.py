# try: codezoo run m07-l11 playground/oops/no-global.py
# changing score inside the function needs `global score`
score = 0


def grab_and_count():
    step(1)
    grab()
    score += 1


for i in range(4):
    grab_and_count()
say(score)
