from dataclasses import dataclass

@dataclass
class Bee:
    name: str

    def work(self):
        say(f"{self.name} rests")

class Worker(Bee):
    def work(self):
        fly(2)
        grab()
        say(f"{self.name} found nectar")

class Guard(Bee):
    def work(self):
        say(f"{self.name} guards")

for bee in [Worker("Bea"), Guard("Gus"), Worker("Ola")]:
    bee.work()
