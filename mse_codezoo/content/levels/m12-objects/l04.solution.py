class Animal:
    def __init__(self, name):
        self.name = name

class Climber(Animal):
    def __init__(self, name, height):
        super().__init__(name)
        self.height = height

c = Climber("Momo", 3)
say(f"{c.name} climbs {c.height}")
