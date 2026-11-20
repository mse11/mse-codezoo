need = {"oak", "pine", "birch"}
for i in range(3):
    step(1)
    grab()
missing = need - set(inventory())
say(missing)
