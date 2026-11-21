def exclaim(func):
    def inner():
        return func() + "!"
    return inner

def twice(func):
    def inner():
        return func() + func()
    return inner

@twice
@exclaim
def greet():
    return "hi"

say(greet())
