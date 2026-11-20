def countdown(n):
    if n == 0:
        say("Go!")
        return
    say(n)
    countdown(n - 1)


countdown(3)
