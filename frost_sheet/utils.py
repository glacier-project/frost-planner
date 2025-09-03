from typing import Any
from rich.console import Console
from rich.rule import Rule

# Initialize the rich console.
_console = Console(markup=True, width=120, force_terminal=True, force_jupyter=False)


def cprint(*args: Any, **kwargs: Any) -> None:
    """
    Custom print function to use rich console.

    Returns:
        None:
            This function does not return any value.
    """
    _console.print(*args, **kwargs)


def cerror(*args: Any, **kwargs: Any) -> None:
    """
    Custom print function for error messages.

    Returns:
        None:
            This function does not return any value.
    """
    _console.print(*args, style="bold red", **kwargs)


def cwarning(*args: Any, **kwargs: Any) -> None:
    """
    Custom print function for warning messages.

    Returns:
        None:
            This function does not return any value.
    """
    _console.print(*args, style="bold yellow", **kwargs)


def crule(*args: Any, **kwargs: Any) -> None:
    """
    Custom print function for rules.

    Returns:
        None:
            This function does not return any value.
    """
    _console.print(Rule(*args, **kwargs))
