import threading

fish = 0
lock = threading.Lock()


def catch_fish():
    global fish
    for _ in range(50):
        with lock:
            seen = fish
            fish = seen + 1


arms = [threading.Thread(target=catch_fish) for _ in range(4)]
for arm in arms:
    arm.start()
for arm in arms:
    arm.join()
print("fish:", fish)
