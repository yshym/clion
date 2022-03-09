from __future__ import annotations
import argparse
import functools
import inspect
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set


def _function_signature(func):
    return inspect.signature(func.__dict__.get("__wrapped__", func))


@dataclass
class Command:
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


class ClionError(Exception):
    pass


class Clion:
    def __init__(self, description: Optional[str] = None):
        self.name = None
        self.description = description
        self._commands: Dict[str, Command] = {}
        self._clions: List[Clion] = []
        self._all_commands: Dict[str, Command] = {}

    def command(self, name=None, aliases=None):
        """Make function a cli command"""

        def decorator_command(command_func):
            command_name = name or command_func.__name__
            command = Command(command_name, command_func, aliases or set())
            self._commands[command_name] = command
            self._all_commands[command_name] = command
            while aliases:
                alias = aliases.pop()
                self._commands[alias] = command
                self._all_commands[alias] = command

            @functools.wraps(command_func)
            def wrapper(*args, **kwargs):
                return command_func(*args, **kwargs)

            return wrapper

        return decorator_command

    def _execute_command(self, name, args, unknown):
        command = self._all_commands.get(name)
        if not command:
            raise ClionError("command does not exist")
        pargs = unknown if command._forwards_arguments else []
        func_signature = _function_signature(command.function)
        for arg in args.__dict__.copy():
            if arg not in func_signature.parameters:
                delattr(args, arg)
        return command.function(*pargs, **vars(args))

    def add_clion(self, clion: Clion, name: str):
        clion.name = name
        self._all_commands.update(clion._commands)
        clion._all_commands = self._all_commands
        self._clions.append(clion)

    @staticmethod
    def _add_command_parser(subparsers, command):
        if not command:
            return None
        parser_data = command._parser_data
        name = parser_data.pop("name")
        return subparsers.add_parser(name, **parser_data)

    def _parser(self, parent_subparsers=None):
        parser = (
            parent_subparsers.add_parser(self.name, help=self.description)
            if parent_subparsers
            else argparse.ArgumentParser(description=self.description)
        )
        subparsers = parser.add_subparsers(
            dest="command", help="command to execute", required=True
        )
        for command_name, command in self._commands.items():
            if command_name in command.aliases:
                continue
            subparser_command = self._add_command_parser(subparsers, command)
            for command_argument in command._args:
                name = command_argument.pop("name")
                subparser_command.add_argument(name, **command_argument)
        for clion in self._clions:
            clion._parser(subparsers)
        return parser

    def __call__(self):
        args, unknown = self._parser().parse_known_args()
        if "command" not in args:
            return None
        command_name = args.command
        del args.command
        return self._execute_command(command_name, args, unknown)
