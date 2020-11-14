# Copyright 2019 The Meson development team

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import typing as T
import hashlib
from .._pathlib import Path, PurePath, PureWindowsPath, PurePosixPath

from .. import mlog
from . import ExtensionModule
from . import ModuleReturnValue
from ..mesonlib import MesonException, MachineChoice
from ..interpreterbase import FeatureNew

from ..interpreterbase import stringArgs, noKwargs, permittedKwargs
if T.TYPE_CHECKING:
    from ..interpreter import Interpreter, ModuleState

class FSModule(ExtensionModule):

    def __init__(self, interpreter: 'Interpreter') -> None:
        super().__init__(interpreter)
        self.snippets.add('generate_dub_file')

    def _absolute_dir(self, state: 'ModuleState', arg: str) -> Path:
        """
        make an absolute path from a relative path, WITHOUT resolving symlinks
        """
        return Path(state.source_root) / Path(state.subdir) / Path(arg).expanduser()

    def _resolve_dir(self, state: 'ModuleState', arg: str) -> Path:
        """
        resolves symlinks and makes absolute a directory relative to calling meson.build,
        if not already absolute
        """
        path = self._absolute_dir(state, arg)
        try:
            # accomodate unresolvable paths e.g. symlink loops
            path = path.resolve()
        except Exception:
            # return the best we could do
            pass
        return path

    def _check(self, check: str, state: 'ModuleState', args: T.Sequence[str]) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.{} takes exactly one argument.'.format(check))
        test_file = self._resolve_dir(state, args[0])
        val = getattr(test_file, check)()
        if isinstance(val, Path):
            val = str(val)
        return ModuleReturnValue(val, [])

    @stringArgs
    @noKwargs
    @FeatureNew('fs.expanduser', '0.54.0')
    def expanduser(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.expanduser takes exactly one argument.')
        return ModuleReturnValue(str(Path(args[0]).expanduser()), [])

    @stringArgs
    @noKwargs
    @FeatureNew('fs.is_absolute', '0.54.0')
    def is_absolute(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.is_absolute takes exactly one argument.')
        return ModuleReturnValue(PurePath(args[0]).is_absolute(), [])

    @stringArgs
    @noKwargs
    @FeatureNew('fs.as_posix', '0.54.0')
    def as_posix(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        """
        this function assumes you are passing a Windows path, even if on a Unix-like system
        and so ALL '\' are turned to '/', even if you meant to escape a character
        """
        if len(args) != 1:
            raise MesonException('fs.as_posix takes exactly one argument.')
        return ModuleReturnValue(PureWindowsPath(args[0]).as_posix(), [])

    @stringArgs
    @permittedKwargs({"within", "native"})
    @FeatureNew('fs.relative_to', '0.57.0')
    def relative_to(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        """
        this function returns a version of the path given by the first argument relative to
        the path given in the second argument.
        If a third path is given in 'within' argument, then the function will return the first
        argument unchanged if it is not within the 'within' path.
        """
        if len(args) != 2:
            raise MesonException('fs.relative_to takes two arguments and optionally a "within" and a "native" argument.')
        # pathlib requires to use PureWindowsPath for Windows paths for absolute and relative
        # path computations
        for_machine = self.interpreter.machine_from_native_kwarg(kwargs)
        if for_machine == MachineChoice.BUILD:
            system = state.build_machine.system
        else:
            system = state.host_machine.system
        if system == "windows":
            path_class = PureWindowsPath  # type: T.Union[T.Type[PurePosixPath], T.Type[PureWindowsPath]]
        else:
            path_class = PurePosixPath
        
        path_to = path_class(args[0])
        if not path_to.is_absolute():
            raise MesonException(f'The first argument ({path_to}) must be an absolute path.')
        path_from = path_class(args[1])
        if not path_from.is_absolute():
            raise MesonException(f'The second argument ({path_from}) must be an absolute path.')
        if "within" in kwargs:
            path_within = path_class(kwargs["within"])
            if not path_within.is_absolute():
                raise MesonException('The "within" argument ({path_within}) must be an absolute path.')
            # Return path_to if it is not relative to path_within
            try:
                path_to.relative_to(path_within)
            except ValueError:
                return ModuleReturnValue(str(path_to), [])
        # If path_to starts with path_from, then .relative_to() provides a solution:
        try:
            x = path_to.relative_to(path_from)
        except ValueError:
            pass
        else:
            return ModuleReturnValue(str(x), [])

        # Get the common root between the two paths:
        parts_to = path_to.parts
        parts_from = path_from.parts
        if parts_to[0] != parts_from[0]:
            raise MesonException(f"{path_to} and {path_from} do not have a common root." +
                                 "Use the \"within\" argument if you want an absolute path instead of an error.")
        parts_root = []
        for part_to, part_from in zip(parts_to, parts_from):
            if part_to != part_from:
                break
            parts_root.append(part_to)
        root = path_class(parts_root[0]) / path_class("/".join(parts_root[1:]))

        # Then find how many levels do we need to go from path_from to the root:
        num_levels = len(path_from.parts) - len(root.parts)
        # And build the final path, going from path_from to the root and then to path_to:
        path = path_class("/".join(num_levels*['..'])) / path_to.relative_to(root)
        return ModuleReturnValue(str(path), [])


    @stringArgs
    @noKwargs
    def exists(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        return self._check('exists', state, args)

    @stringArgs
    @noKwargs
    def is_symlink(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.is_symlink takes exactly one argument.')
        return ModuleReturnValue(self._absolute_dir(state, args[0]).is_symlink(), [])

    @stringArgs
    @noKwargs
    def is_file(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        return self._check('is_file', state, args)

    @stringArgs
    @noKwargs
    def is_dir(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        return self._check('is_dir', state, args)

    @stringArgs
    @noKwargs
    def hash(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 2:
            raise MesonException('fs.hash takes exactly two arguments.')
        file = self._resolve_dir(state, args[0])
        if not file.is_file():
            raise MesonException('{} is not a file and therefore cannot be hashed'.format(file))
        try:
            h = hashlib.new(args[1])
        except ValueError:
            raise MesonException('hash algorithm {} is not available'.format(args[1]))
        mlog.debug('computing {} sum of {} size {} bytes'.format(args[1], file, file.stat().st_size))
        h.update(file.read_bytes())
        return ModuleReturnValue(h.hexdigest(), [])

    @stringArgs
    @noKwargs
    def size(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.size takes exactly one argument.')
        file = self._resolve_dir(state, args[0])
        if not file.is_file():
            raise MesonException('{} is not a file and therefore cannot be sized'.format(file))
        try:
            return ModuleReturnValue(file.stat().st_size, [])
        except ValueError:
            raise MesonException('{} size could not be determined'.format(args[0]))

    @stringArgs
    @noKwargs
    def is_samepath(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 2:
            raise MesonException('fs.is_samepath takes exactly two arguments.')
        file1 = self._resolve_dir(state, args[0])
        file2 = self._resolve_dir(state, args[1])
        if not file1.exists():
            return ModuleReturnValue(False, [])
        if not file2.exists():
            return ModuleReturnValue(False, [])
        try:
            return ModuleReturnValue(file1.samefile(file2), [])
        except OSError:
            return ModuleReturnValue(False, [])

    @stringArgs
    @noKwargs
    def replace_suffix(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 2:
            raise MesonException('fs.replace_suffix takes exactly two arguments.')
        original = PurePath(args[0])
        new = original.with_suffix(args[1])
        return ModuleReturnValue(str(new), [])

    @stringArgs
    @noKwargs
    def parent(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.parent takes exactly one argument.')
        original = PurePath(args[0])
        new = original.parent
        return ModuleReturnValue(str(new), [])

    @stringArgs
    @noKwargs
    def name(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.name takes exactly one argument.')
        original = PurePath(args[0])
        new = original.name
        return ModuleReturnValue(str(new), [])

    @stringArgs
    @noKwargs
    @FeatureNew('fs.stem', '0.54.0')
    def stem(self, state: 'ModuleState', args: T.Sequence[str], kwargs: dict) -> ModuleReturnValue:
        if len(args) != 1:
            raise MesonException('fs.stem takes exactly one argument.')
        original = PurePath(args[0])
        new = original.stem
        return ModuleReturnValue(str(new), [])

def initialize(*args: T.Any, **kwargs: T.Any) -> FSModule:
    return FSModule(*args, **kwargs)
