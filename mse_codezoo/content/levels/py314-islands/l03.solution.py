class Queen:
    def boss_of(self) -> Worker:
        return Worker("Bea")

class Worker:
    def __init__(self, name: str) -> None:
        self.name = name

say(Queen().boss_of().name)
