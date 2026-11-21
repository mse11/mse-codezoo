def times(n):
    def decorate(move):
        def repeat(*args):
            for _ in range(n):
                move(*args)
        return repeat
    return decorate

@times(3)
def sneak():
    hide()
    step(1)

sneak()
grab()
