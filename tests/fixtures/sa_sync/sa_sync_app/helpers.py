CLOSED: list[str] = []


class Greeting:
    def __init__(self) -> None:
        self.text = "hi"

    def close(self) -> None:
        CLOSED.append("greeting")


def make_greeting() -> Greeting:
    return Greeting()


def extra_names(namespace: dict) -> dict:
    return {"book_count": lambda: namespace["session"].query(namespace["Book"]).count()}
