"""
.. module:: colors
   :synopsis: Functions for coloring text using ansi codes

.. moduleauthor:: Steven Arcangeli <steven@highlig.ht>

Functions for coloring text using ansi codes

"""

def _color_wrap(termcode):
    """ Create a color-wrapper function for a specific termcode color """
    return lambda x: "\033[{}m{}\033[0m".format(termcode, x)

#pylint: disable=C0103
red, green, yellow, blue, magenta, cyan, white = \
    map(_color_wrap, range(31, 38))
