import threading

def gather(arm):
    for _ in range(3):
        wiggle = arm
    stretch(arm)

arms = [threading.Thread(target=gather, args=(arm,)) for arm in (0, 2, 4, 6)]
for arm in arms:
    arm.start()
for arm in arms:
    arm.join()
