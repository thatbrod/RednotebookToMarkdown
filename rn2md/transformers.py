"""Helpers to tranform data in RedNotebook-syntax to Markdown-syntax.

Here is a summary of the currently implemented transformers:

    RedNotebook                       Markdown
    ===========                       ========
    [name ""url""]                    [name](url)
    //text//                          _text_
    --text--                          ~text~
    =Text=                            # Text
    [""url""]                         ![...](url)
    + Ordered item                    1. Ordered item
    - Unordered item                  - Unordered item
    ``asdf``                          `asdf`
"""
import re

import defaultlist


class TransformerBase():
    """Handles boilerplate required by all transformers."""

    def __init__(self):
        self._transformer = self.transformer_generator()
        # Initialize generator coroutine by calling `next` once on it.
        _ = next(self._transformer, None)

    def fmt(self, line):
        """Returns the given RedNotebook line in Markdown format."""
        return self._transformer.send(line)

    def transformer_generator(self):
        """Generator for subclasses to format RedNotebook text as Markdown."""
        raise NotImplementedError


class LinkTransformer(TransformerBase):
    """Transform links from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms '[[text ""url""]]' to '[text](url)'."""
        line = ''
        while True:
            line = yield re.sub(r'\[([^\]]*?) ""(.*?)""\]', r'[\1](\2)', line)


class ItalicTransformer(TransformerBase):
    """Transform italics from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms '//text//' to '_text_'."""
        line = ''
        while True:
            line = yield _sub_balanced_delims('//', '_', line)


class StrikethroughTransformer(TransformerBase):
    """Transform strikethroughs from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms '--text--' to '**OBSOLETE**(text)'."""
        line = ''
        while True:
            line = yield (
                line if set(line) == {'-'} else
                _sub_balanced_delims('--', ('**OBSOLETE**(', ')'), line,
                                     op=lambda d: d.rstrip('.?!')))


class CodeBlockTransformer(TransformerBase):
    """Transform code blocks from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms codeblocks into markdown-syntax."""
        line = ''
        while True:
            line = yield _sub_balanced_delims('``', '`', line,
                                              preds=[_not_in_link])


class HeaderTransformer(TransformerBase):
    """Transform headers from RedNotebook-syntax to Markdown-syntax."""

    def __init__(self, init_level=0):
        """Constructor.

        Args:
            init_level: additional levels to add to all headers.
        """
        self._init_level = init_level
        super().__init__()

    def transformer_generator(self):
        """Transforms '=TEXT=' into '# TEXT'."""
        line = ''
        while True:
            line = yield line
            start_delim = re.search(r'^=+', line)
            if not start_delim or start_delim.group() == line:
                continue
            end_delim = re.search(r'=+$', line)
            if not end_delim or end_delim.group() != start_delim.group():
                continue
            lvl = len(start_delim.group())
            line = f'{"#" * (self._init_level + lvl)} {line[lvl:-lvl].lstrip()}'


class ListTransformer(TransformerBase):
    """Transform lists from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms ordered and unordered lists into markdown-syntax."""
        line = ''
        ordered_list_history = defaultlist.defaultlist(lambda: 1)
        sequential_empty_lines = 0
        while True:
            line = yield line
            li_match = re.match(r'^\s*([-|\+])\s', line)
            if li_match:
                i = li_match.start(1)
                # Always clear sub-items so they restart their numbering.
                del ordered_list_history[i + 1:]
                if line[i] == '-':
                    pass  # Un-ordered lists use same format in markdown.
                else:
                    # Ordered lists should change to their actual number.
                    line = f'{line[:i]}{ordered_list_history[i]}.{line[i + 1:]}'
                    ordered_list_history[i] += 1
            elif line.strip():
                sequential_empty_lines = 0
                ordered_list_history.clear()
            else:
                sequential_empty_lines += 1
                if sequential_empty_lines >= 2:
                    ordered_list_history.clear()


class InnerUnderscoreEscaper(TransformerBase):
    """Transform underscores from RedNotebook-syntax to Markdown-syntax."""

    def transformer_generator(self):
        """Transforms underscores which need to be escaped."""
        line = ''
        while True:
            line = yield line
            inner_underscores = list(_filter_matches(r'(?<=\w)_(?=\w)', line))
            for match in reversed(inner_underscores):
                line = f'{line[:match.start()]}\\_{line[match.end():]}'


def _sub_balanced_delims(delim_pattern, sub, string, op=str, **kwargs):
    """Finds paired delimiters and replaces them with a substitution.

    Example:
        >>> _sub_balanced_delims('*', '_', '^ *test* $', op=lambda s: s.upper())
        ... '^ _TEST_ $'

    Args:
        delim_pattern: regex for the delimiter to replace.
        sub: delimiter to use instead. Can either be a string or a 2-tuple.
        string: string to have delimiters replaced.
        op: function to transform strings between delimiters. Defaults to no-op.
        **kwargs: downstream arguments for _filter_matches.

    Returns:
        new string where all targeted balanced delimiters are substituted.
    """
    try:
        start_sub, end_sub = sub
    except ValueError:
        start_sub = end_sub = sub
    delims = _filter_matches(delim_pattern, string, **kwargs)
    balanced_delims = list(zip(delims, delims))
    # NOTE: Do substitutions in reverse so the match indices stay valid.
    for start_delim, end_delim in reversed(balanced_delims):
        start = string[:start_delim.start()]
        data = string[start_delim.end():end_delim.start()]
        end = string[end_delim.end():]
        string = f'{start}{start_sub}{op(data)}{end_sub}{end}'
    return string


def _filter_matches(pattern, string, preds=None):
    if preds is None:
        preds = (_not_in_link, _not_in_backticks)
    return (m for m in re.finditer(pattern, string) if all(p(m) for p in preds))


def _not_in_link(match):
    links = re.finditer(r'\[([^\]]*?) ""(.*?)""\]', match.string)
    return not any(_spans_intersect(match.span(), m.span(2)) for m in links)


def _not_in_backticks(match):
    backticks = re.finditer(r'`.*?`', match.string)
    return not any(_spans_intersect(match.span(), m.span()) for m in backticks)


def _spans_intersect(span1, span2):
    (lo1, hi1), (lo2, hi2) = span1, span2
    return hi1 >= lo2 and hi2 >= lo1
