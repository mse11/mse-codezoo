best_name, best = "", -1
with open("scores.txt") as file:
    for line in file:
        name, score = line.split()
        if int(score) > best:
            best_name, best = name, int(score)
say(f"{best_name} {best}")
