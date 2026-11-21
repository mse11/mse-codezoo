import functools

def logged(func):
    @functools.wraps(func)
    def inner(*args, **kwargs):
        say(f"start {func.__name__}")
        return func(*args, **kwargs)
    return inner

@logged
def dig(depth):
    step(depth)

dig(2)
grab()
say(dig.__name__)
