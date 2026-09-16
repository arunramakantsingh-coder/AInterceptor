from prompt_toolkit.completion import Completer, Completion


GLOBAL_COMMANDS = [
    "help",
    "providers",
    "status",
    "use",
    "sessions",
    "diagnostics",
    "version",
    "clear",
    "exit",
    "quit",
]

PROVIDER_COMMANDS = [
    "help",
    "status",
    "session",
    "chat",
    "diagnostics",
    "doctor",
    "back",
    "exit",
    "quit",
]


class AInterceptorCompleter(Completer):
    def __init__(self, shell):
        self.shell = shell

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        word = document.get_word_before_cursor()

        if self.shell.provider is None:
            commands = GLOBAL_COMMANDS

            # Provider aliases.
            if text.startswith("use "):
                prefix = word.lower()
                for provider in self.shell.providers:
                    if provider.name.startswith(prefix):
                        yield Completion(
                            provider.name,
                            start_position=-len(word),
                        )
                return

        else:
            commands = PROVIDER_COMMANDS

        prefix = word.lower()

        for command in commands:
            if command.startswith(prefix):
                yield Completion(
                    command,
                    start_position=-len(word),
                )
