import argparse
import functools
import inspect
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Set


def _function_signature(func):
    return inspect.signature(func.__dict__.get("__wrapped__", func))


class Hashable:
    def __hash__(self):
        return hash(self.__dict__.values())


@dataclass(eq=False)
class Command(Hashable):
    name: str
    function: Callable
    aliases: Set[str]

    @property
    def _args(self):
        arguments = []
        signature = _function_signature(self.function)
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
            argument["help"] = self._parameter_docs.get(param.name)
            arguments.append(argument)
        return arguments

    @property
    def _forwards_arguments(self):
        return str(_function_signature(self.function)) in {
            "(*args)",
            "(*args, **kwargs)",
        }

    @property
    def _doc(self):
        doc = self.function.__doc__
        return doc.split("\n\n", maxsplit=1)[0].strip() if doc else None

    @property
    def _parameter_docs(self):
        if not self.function.__doc__:
            return {}
        docs = re.split(r"-+", self.function.__doc__)
        if len(docs) < 2:
            return {}
        doc = docs[1]
        param_docs = re.findall(r"(?P<name>\w+)\n\s*(?P<doc>.+)\n", doc)
        return dict(param_docs)

    @property
    def _parser_data(self):
        return {"name": self.name, "aliases": self.aliases, "help": self._doc}


@dataclass(eq=False)
class Action(Command):
    command: Command


class ClionError(Exception):
    pass


class Clion:
    def __init__(self):
        self._commands: Dict[str, Command] = {}
        self._actions: Dict[str, Dict[str, Action]] = defaultdict(dict)

    def command(self, aliases=None):
        """Make function a cli command"""

        def decorator_command(command_func):
            command_name = command_func.__name__
            command = Command(command_name, command_func, aliases or set())
            self._commands[command_name] = command
            while aliases:
                self._commands[aliases.pop()] = command

            def action(aliases=None):
                """Make function an action of a cli command"""

                def decorator_action(action_func):
                    _, action_name = action_func.__name__.split("_")
                    action = Action(
                        action_name, action_func, aliases or set(), command
                    )
                    self._actions[command_name][action_name] = action
                    while aliases:
                        self._actions[command_name][aliases.pop()] = action

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

    @staticmethod
    def _func_from_command_and_action(command, action=None):
        return action.function if action else command.function

    def _execute_command(self, command, args, unknown):
        command = self._commands.get(command)
        if not command:
            raise ClionError("command does not exist")
        action = None
        if "action" in args and args.action:
            action = self._actions.get(command.name, {}).get(args.action)
            del args.action
        entity = action or command
        pargs = unknown if entity._forwards_arguments else []
        func_signature = _function_signature(entity.function)
        for arg in args.__dict__.copy():
            if arg not in func_signature.parameters:
                delattr(args, arg)
        return entity.function(*pargs, **vars(args))

    @staticmethod
    def _add_parser(subparsers, command, action=None):
        if not command and not action:
            return None
        parser_data = action._parser_data if action else command._parser_data
        name = parser_data.pop("name")
        return subparsers.add_parser(name, **parser_data)

    def _parse_args(self):
        parser = argparse.ArgumentParser(description="Nix helper")
        if not self._commands:
            return parser.parse_known_args()
        subparsers = parser.add_subparsers(
            dest="command", help="command to execute", required=True
        )
        for command_name, command in self._commands.items():
            if command_name in command.aliases:
                continue
            subparser_command = self._add_parser(subparsers, command)
            for command_argument in command._args:
                name = command_argument.pop("name")
                subparser_command.add_argument(name, **command_argument)
            if not self._actions[command.name]:
                continue
            subparsers_command_actions = subparser_command.add_subparsers(
                dest="action", help="action to do"
            )
            for action_name, action in self._actions[command.name].items():
                if action_name in action.aliases:
                    continue
                subparser_action = self._add_parser(
                    subparsers_command_actions, command, action
                )
                for action_argument in action._args:
                    name = action_argument.pop("name")
                    subparser_action.add_argument(name, **action_argument)
        return parser.parse_known_args()

    def __call__(self):
        args, unknown = self._parse_args()
        if "command" not in args:
            return None
        command = args.command
        del args.command
        return self._execute_command(command, args, unknown)
