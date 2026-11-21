from hive import Bee

class Worker(Bee):
    def work(self):
        fly(2)
        grab()

class Drone(Bee):
    pass

for bee in [Drone("Dan"), Worker("Bea")]:
    bee.work()
