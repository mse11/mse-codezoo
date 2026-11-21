name = input("Name? ")
score = input("Score? ")
with open("scores.txt", "a") as file:
    file.write(f"{name} {score}\n")
