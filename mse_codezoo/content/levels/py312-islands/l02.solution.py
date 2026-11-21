type Load = list[str]

class Stack[T]:
    def __init__(self) -> None:
        self.items: list[T] = []

    def push(self, item: T) -> None:
        self.items.append(item)

    def pop(self) -> T:
        return self.items.pop()

logs = Stack()
logs.push("oak")
logs.push("pine")
say(logs.pop())
