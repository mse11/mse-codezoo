class Helper:
    def __init__(self, name):
        self.name = name

    def greet(self):
        say(f"I am {self.name}")

Helper("Momo").greet()
