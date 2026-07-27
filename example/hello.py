"""Example hello module providing greeting functionality.

This module demonstrates proper Python practices including type annotations,
docstrings, and the if __name__ == '__main__' guard.
"""


def greet(name: str = "World") -> str:
    """Generate a greeting message for the given name.

    Args:
        name: The name to greet. Defaults to "World".

    Returns:
        A greeting string.
    """
    return f"Hello, {name}!"


def main() -> None:
    """Print a default greeting to standard output."""
    print(greet())


if __name__ == "__main__":
    main()
