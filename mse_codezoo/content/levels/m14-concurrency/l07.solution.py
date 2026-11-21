import threading

shells = 0
lock = threading.Lock()

def gather():
    global shells
    for _ in range(5):
        with lock:
            seen = shells
            shells = seen + 1

arms = [threading.Thread(target=gather) for _ in range(4)]
for arm in arms:
    arm.start()
for arm in arms:
    arm.join()
say(shells)
