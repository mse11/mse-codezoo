# try: codezoo run m10-l01 playground/oops/no-base-case.py
# countdown never stops: no base case
def countdown(n):
    say(n)
    countdown(n - 1)


countdown(3)
