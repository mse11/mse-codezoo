plan = {"oak": 2, "pine": 1}
for i in range(4):
    step(1)
    grab()
for log, count in plan.items():
    for i in range(count):
        build(log)
        step(1)
