class Climber:
    def move(self):
        return "climb"

class Swimmer:
    def move(self):
        return "swim"

class Otter(Swimmer, Climber):
    pass

say(Otter().move())
say([c.__name__ for c in Otter.__mro__])
