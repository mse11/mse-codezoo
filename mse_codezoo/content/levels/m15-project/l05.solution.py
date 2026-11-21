questions = {"2 + 3": "5", "4 * 2": "8", "9 - 6": "3"}
points = 0
for question, answer in questions.items():
    reply = input(f"{question} = ")
    if reply == answer:
        points += 1
say(f"{points} points")
with open("highscore.txt", "w") as file:
    file.write(str(points))
