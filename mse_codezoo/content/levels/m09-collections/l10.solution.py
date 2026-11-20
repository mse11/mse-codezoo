plan = {"oak": 1, "pine": 2}
while not is_blocked():
    step(1)
    grab()
for log, count in plan.items():
    for i in range(count):
        build(log)
        step(1)
say(inventory())
