# m01-l03 "Around the rock": go down, along the bottom, then back up
turn_right()  # now facing south
step(1)       # (0, 1)
turn_left()   # now facing east
step(2)       # (2, 1)
turn_left()   # now facing north
step(1)       # (2, 0), on the banana
grab()
