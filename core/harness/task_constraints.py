import re


class TaskConstraints:

    def __init__(self):
        self.allow_install = True
        self.allow_system_changes = True
        self.allow_destructive = True

    @classmethod
    def from_task(cls, task: str):
        constraints = cls()

        text = task.lower()

        no_install_patterns = [
            r"\bnão instale\b",
            r"\bnão instalar\b",
            r"\bnao instale\b",
            r"\bnao instalar\b",
            r"\bsem instalar\b",
            r"\bapenas verifique\b",
            r"\bsomente verifique\b",
        ]

        no_system_change_patterns = [
            r"\bnão altere o sistema\b",
            r"\bnão alterar o sistema\b",
            r"\bnao altere o sistema\b",
            r"\bnao alterar o sistema\b",
            r"\bsem alterar o sistema\b",
        ]

        no_destructive_patterns = [
            r"\bnão remova\b",
            r"\bnão delet",
            r"\bnão apague\b",
            r"\bnao remova\b",
            r"\bnao delet",
            r"\bnao apague\b",
        ]

        if any(re.search(pattern, text) for pattern in no_install_patterns):
            constraints.allow_install = False

        if any(re.search(pattern, text) for pattern in no_system_change_patterns):
            constraints.allow_system_changes = False

        if any(re.search(pattern, text) for pattern in no_destructive_patterns):
            constraints.allow_destructive = False

        return constraints

    def summary(self):
        return {
            "allow_install": self.allow_install,
            "allow_system_changes": self.allow_system_changes,
            "allow_destructive": self.allow_destructive,
        }
