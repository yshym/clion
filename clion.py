import argparse
import functools
import inspect
import re
from collections import defaultdict


class ClionCommandNotExists(Exception):
    pass


class Clion:
    def __init__(self):
        self._commands = {}
        self._command_aliases = {}
        self._actions = defaultdict(dict)
        self._action_aliases = defaultdict(dict)

    def command(self, aliases=None):
        """Make function a cli command"""

        def decorator_command(command_func):
            command_name = command_func.__name__
            self._commands[command_name] = command_func
            while aliases:
                self._command_aliases[aliases.pop()] = command_name

            def action(aliases=None):
                """Make function an action of a cli command"""

                def decorator_action(action_func):
                    _, action_name = action_func.__name__.split("_")
                    self._actions[command_name][action_name] = action_func
                    while aliases:
                        self._action_aliases[command_name][
                            aliases.pop()
                        ] = action_name

                    @functools.wraps(action_func)
                    def wrapper(*args, **kwargs):
                        action_func(*args, **kwargs)

                    return wrapper

                return decorator_action

            command_func.action = action

            @functools.wraps(command_func)
            def wrapper(*args, **kwargs):
                return command_func(*args, **kwargs)

            return wrapper

        return decorator_command

    def aliases_from_command(self, command):
        return [
            al for al, com in self._command_aliases.items() if com == command
        ]

    def aliases_from_action(self, command, action):
        return [
            al
            for al, ac in self._action_aliases[command].items()
            if ac == action
        ]

    @staticmethod
    def command_forwards_arguments(f):
        return str(inspect.signature(f)) in {"(*args)", "(*args, **kwargs)"}

    def is_command(self, command):
        return command in self._commands

    def execute_command(self, command, args, unknown):
        if (
            command not in self._commands
            and command not in self._command_aliases
        ):
            raise ClionCommandNotExists("command does not exist")
        command = self._command_aliases.get(command, command)
        action = None
        if "action" in args:
            action = (
                self._action_aliases.get(command).get(args.action)
                or args.action
            )
            del args.action
        func = (
            self._actions[command][action]
            if action
            else self._commands[command]
        )
        pargs = unknown if self.command_forwards_arguments(func) else []
        return func(*pargs, **vars(args))

    def add_parser(self, subparsers, name, command=None):
        aliases = (
            self.aliases_from_action(command, name)
            if command
            else self.aliases_from_command(name)
        )
        func = (
            self._actions[command][name] if command else self._commands[name]
        )
        doc = func.__doc__
        help_ = doc.split("\n\n", maxsplit=1)[0].strip() if doc else None
        return subparsers.add_parser(name, aliases=aliases, help=help_)

    @staticmethod
    def parameter_docs(func):
        if not func.__doc__:
            return {}
        docs = re.split(r"-+", func.__doc__)
        if len(docs) < 2:
            return {}
        doc = docs[1]
        param_docs = re.findall(r"(?P<name>\w+)\n\s*(?P<doc>.+)\n", doc)
        return dict(param_docs)

    def args_from_function(self, name: str, command=None):
        arguments = []
        func = (
            self._actions[command][name] if command else self._commands[name]
        )
        signature = inspect.signature(func.__dict__.get("__wrapped__", func))
        for param in signature.parameters.values():
            if str(param)[0] == "*":
                continue
            argument = {}
            argument["name"] = param.name
            has_annotation = param.annotation is not param.empty
            type_ = param.annotation if has_annotation else None
            if (
                type_
                and hasattr(type_, "__origin__")
                and type_.__origin__ in {list, tuple, set}
            ):
                type_ = (
                    type_.__args__[0] if hasattr(type_, "__args__") else None
                )
                argument["nargs"] = "+"
            argument["type"] = type_
            has_default_value = param.default is not param.empty
            argument["default"] = param.default if has_default_value else None
            if has_default_value:
                argument["nargs"] = "?"
            argument["help"] = self.parameter_docs(func).get(param.name)
            arguments.append(argument)
        return arguments

    def parse_args(self):
        parser = argparse.ArgumentParser(description="Nix helper")
        if not self._commands:
            return parser.parse_known_args()
        subparsers = parser.add_subparsers(
            dest="command", help="command to execute", required=True
        )
        for command in self._commands:
            subparser_command = self.add_parser(subparsers, command)
            for command_argument in self.args_from_function(command):
                name = command_argument.pop("name")
                subparser_command.add_argument(name, **command_argument)
            if not self._actions[command]:
                continue
            subparsers_command_actions = subparser_command.add_subparsers(
                dest="action", help="action to do", required=True
            )
            for action in self._actions[command]:
                subparser_action = self.add_parser(
                    subparsers_command_actions, action, command
                )
                for action_argument in self.args_from_function(
                    action, command=command
                ):
                    name = action_argument.pop("name")
                    subparser_action.add_argument(name, **action_argument)
        return parser.parse_known_args()

    def __call__(self):
        args, unknown = self.parse_args()
        if "command" not in args:
            return None
        command = args.command
        del args.command
        return self.execute_command(command, args, unknown)
