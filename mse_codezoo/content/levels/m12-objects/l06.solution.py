from dataclasses import dataclass

@dataclass
class Log:
    kind: str
    length: float = 1.0

logs = [Log("oak", 2.5), Log("pine")]
say(logs[1])
