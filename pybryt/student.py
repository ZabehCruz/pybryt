"""Student implementations for PyBryt"""

import os
import dill
import base64
import nbformat
import inspect

from contextlib import contextmanager
from typing import Any, List, NoReturn, Optional, Tuple, Union

from .execution import create_collector, _currently_tracing, execute_notebook, tracing_off, tracing_on
from .reference import ReferenceImplementation, ReferenceResult


NBFORMAT_VERSION = 4


class StudentImplementation:
    """
    A student implementation class for handling the execution of student work and manging the 
    memory footprint generated by that execution.

    Args:
        path_or_nb (``str`` or ``nbformat.NotebookNode``): the submission notebook or the path to it
        addl_filenames (``list[str]``, optional): additional filenames to trace inside during 
            execution
        output (``str``, optional): a path at which to write executed notebook
    """

    nb: Optional[nbformat.NotebookNode]
    """the submission notebook"""

    nb_path: Optional[str]
    """the path to the notebook file"""

    values: List[Tuple[Any, int]]
    """the memory footprint (a list of tuples of objects and their timestamps)"""

    steps: int
    """number of execution steps"""

    def __init__(
        self, path_or_nb: Optional[Union[str, nbformat.NotebookNode]], addl_filenames: List[str] = [],
        output: Optional[str] = None
    ):
        if path_or_nb is None:
            self.nb = None
            self.nb_path = None
            return
        if isinstance(path_or_nb, str):
            self.nb = nbformat.read(path_or_nb, as_version=NBFORMAT_VERSION)
            self.nb_path = path_or_nb
        elif isinstance(path_or_nb, nbformat.NotebookNode):
            self.nb = path_or_nb
            self.nb_path = ""
        else:
            raise TypeError(f"path_or_nb is of unsupported type {type(path_or_nb)}")

        self._execute(addl_filenames=addl_filenames, output=output)

    def _execute(self, addl_filenames: List[str] = [], output: Optional[str] = None) -> NoReturn:
        """
        Executes the notebook ``self.nb``.

        Args:
            addl_filenames (``list[str]``, optional): additional filenames to trace inside during 
                execution
            output (``str``, optional): a path at which to write executed notebook
        """
        self.steps, self.values = execute_notebook(
            self.nb, self.nb_path, addl_filenames=addl_filenames, output=output
        )

    @classmethod
    def from_footprint(cls, footprint, steps):
        """
        """
        stu = cls(None)
        stu.steps = steps
        stu.values = footprint
        return stu

    def dump(self, dest: str = "student.pkl") -> NoReturn:
        """
        Pickles this student implementation to a file.

        Args:
            dest (``str``, optional): the path to the file
        """
        with open(dest, "wb+") as f:
            dill.dump(self, f)

    def dumps(self) -> str:
        """
        Pickles this student implementation to a base-64-encoded string.

        Returns:
           ``str``: the pickled and encoded student implementation
        """
        bits = dill.dumps(self)
        return base64.b64encode(bits).decode("ascii")

    @staticmethod
    def load(file: str) -> Union['StudentImplementation']:
        """
        Unpickles a student implementation from a file.

        Args:
            file (``str``): the path to the file
        
        Returns:
            :py:class:`StudentImplementation<pybryt.StudentImplementation>`: the unpickled student 
            implementation
        """
        with open(file, "rb") as f:
            instance = dill.load(f)
        return instance

    @classmethod
    def loads(cls, data: str) -> "StudentImplementation":
        """
        Unpickles a student implementation from a base-64-encoded string.

        Args:
            data (``str``): the pickled and encoded student implementation
        
        Returns:
            :py:class:`StudentImplementation<pybryt.StudentImplementation>`: the unpickled student 
            implementation
        """
        return dill.loads(base64.b64decode(data.encode("ascii")))

    def check(self, ref: Union[ReferenceImplementation, List[ReferenceImplementation]], group=None) -> \
            Union[ReferenceResult, List[ReferenceResult]]:
        """
        Checks this student implementation against a single or list of reference implementations.
        Returns the :py:class:`ReferenceResult<pybryt.ReferenceResult>` object(s) resulting from 
        those checks.

        Args:
            ref (``ReferenceImplementation`` or ``list[ReferenceImplementation]``): the reference(s)
                to run against
            group (``str``, optional): if specified, only annotations in this group will be run

        Returns:
            ``ReferenceResult`` or ``list[ReferenceResult]``: the results of the reference 
            implementation checks
        """
        if isinstance(ref, ReferenceImplementation):
            return ref.run(self.values, group=group)
        elif isinstance(ref, list):
            return [r.run(self.values, group=group) for r in ref]
        else:
            raise TypeError(f"check cannot take values of type {type(ref)}")

    def check_plagiarism(self, student_impls: List["StudentImplementation"], **kwargs) -> List[ReferenceResult]:
        """
        Checks this student implementation against a list of other student implementations for 
        plagiarism. Uses :py:meth:`create_references<pybryt.plagiarism.create_references>` to create
        a randomly-generated reference implementation from this student implementation and runs it
        against each of the implementations in ``student_impls`` using 
        :py:meth:`get_impl_results<pybryt.plagiarism.get_impl_results>`.

        Args:
            student_impls (``list[StudentImplementation]``): other student implementations to run
                against
            **kwargs: keyword arguments passed to 
                :py:meth:`create_references<pybryt.plagiarism.create_references>` and 
                :py:meth:`get_impl_results<pybryt.plagiarism.get_impl_results>`
        
        Returns:
            ``list[ReferenceResult]`` or ``numpy.ndarray``: the results of each student 
            implementation in ``student_impls`` when run against this student implementation
        """
        refs = create_references([self], **kwargs)
        return get_impl_results(refs[0], student_impls, **kwargs)


@contextmanager
def check(ref, **kwargs):
    """
    """
    if _currently_tracing():
        yield  # if already tracing, no action required

    if isinstance(ref, str):
        ref = [ReferenceImplementation.load(ref)]
    if isinstance(ref, list):
        if len(ref) == 0:
            raise ValueError("Cannot check against an empty list of references")
        if not all(isinstance(r, ReferenceImplementation) for r in ref):
            if not all(isinstance(r, str) for r in ref):
                raise TypeError("Invalid values in the reference list")
            ref = [ReferenceImplementation.load(r) for r in ref]
    if not all(isinstance(r, ReferenceImplementation) for r in ref):
        raise TypeError("Invalid values provided for reference(s)")

    observed, cir = create_collector(**kwargs)
    frame = inspect.currentframe().f_back.f_back

    tracing_on(frame=frame, tracing_func=cir)

    yield

    tracing_off(frame=frame, save_func=False)

    stu = StudentImplementation.from_footprint(observed, max(t[1] for t in observed))
    res = stu.check(ref)
    print([r.messages for r in res])


from .plagiarism import create_references, get_impl_results
