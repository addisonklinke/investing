"""Utility objects that don't fit neatly into another module"""

import argparse
from itertools import filterfalse, tee
import math


def partition(it, pred):
    """Split an iterable base on a predicate

    From Python3 itertool's recipes
    https://docs.python.org/dev/library/itertools.html#itertools-recipes

    :param iterable it: Variable to split
    :param callable pred: Predicte evaluating to boolean
    :return tuple(list): First element meets condition, while second does not
    """
    t1, t2 = tee(it)
    matches = list(filter(pred, t2))
    others = list(filterfalse(pred, t1))
    return matches, others


def ptable_to_csv(table, filename, headers=True):
    """Save PrettyTable results to a CSV file.

    Adapted from @AdamSmith https://stackoverflow.com/questions/32128226

    :param PrettyTable table: Table object to get data from.
    :param str filename: Filepath for the output CSV.
    :param bool headers: Whether to include the header row in the CSV.
    :return: None
    """
    raw = table.get_string()
    data = [tuple(filter(None, map(str.strip, splitline)))
            for line in raw.splitlines()
            for splitline in [str(line).split('|')] if len(splitline) > 1]
    if hasattr(table, 'title') and table.title is not None:
        data = data[1:]
    if not headers:
        data = data[1:]
    with open(filename, 'w') as f:
        for d in data:
            f.write('{}\n'.format(','.join(d)))


def sort_with_na(x, reverse=False, na_last=True):
    """Intelligently sort iterable with NA values

    Adapted from https://stackoverflow.com/q/4240050/7446465

    For reliable behavior with NA values, we should change the NAs to +/- inf
    to guarantee their order rather than relying on the built-in
    ``sorted(reverse=True)`` which will have no effect. To use the ``reverse``
    parameter or other kwargs, use functools.partial in your lambda i.e.

        sorted(iterable, key=partial(sort_with_na, reverse=True, na_last=False))

    :param x: Element to be sorted
    :param bool na_last: Whether NA values should come last or first
    :param bool reverse: Return ascending if ``False`` else descending
    :return bool: Lower ordered element
    """
    if not math.isnan(x):
        return -x if reverse else x
    else:
        return float('inf') if na_last else float('-inf')


class SubCommandDefaults(argparse.ArgumentDefaultsHelpFormatter):
    """Corrected _max_action_length for the indenting of subactions

    This is a known bug (https://bugs.python.org/issue25297) in Python's argparse
    with a patch solution provided from https://stackoverflow.com/a/32891625/7446465
    """
    def add_argument(self, action):
        if action.help is not argparse.SUPPRESS:

            # Find all invocations
            get_invocation = self._format_action_invocation
            invocations = [get_invocation(action)]
            current_indent = self._current_indent
            for subaction in self._iter_indented_subactions(action):
                # compensate for the indent that will be added
                indent_chg = self._current_indent - current_indent
                added_indent = 'x'*indent_chg
                invocations.append(added_indent+get_invocation(subaction))

            # Update the maximum item length
            invocation_length = max([len(s) for s in invocations])
            action_length = invocation_length + self._current_indent
            self._action_max_length = max(self._action_max_length, action_length)

            # Add the item to the list
            self._add_item(self._format_action, [action])
