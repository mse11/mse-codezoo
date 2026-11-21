def hop():
    step(1)

moves = [hop, hop, grab]
for move in moves:
    move()
