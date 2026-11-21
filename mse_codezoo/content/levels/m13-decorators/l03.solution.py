def sneaky(move):
    def quiet(*args):
        hide()
        move(*args)
    return quiet

@sneaky
def sneak():
    step(1)

for _ in range(3):
    sneak()
grab()
